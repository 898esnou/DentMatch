"""
Búsqueda semántica para el paciente ("Haz tu consulta"):
- POST /api/busqueda   {"texto": "...", "solicitud_id": opcional}

Relaciona lo que escribe el paciente con procedimientos del catálogo
(app/datos/procedimientos.json) y devuelve:
  1. los procedimientos relacionados (con su área),
  2. los estudiantes verificados con un requerimiento ABIERTO y cupos pendientes
     en esas áreas, con el mismo formato (EstudianteOut) que /api/estudiantes.

NO diagnostica ni recomienda tratamientos: solo conecta palabras con el catálogo.
El texto del paciente no se guarda ni se escribe en los logs.
"""
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.busqueda_semantica import BuscadorNoDisponible, buscar
from app.catalogos import AREAS
from app.database import get_db
from app.routers.estudiantes import _cargar, _estados_para_solicitud, _out
from app.schemas_dominio import EstudianteOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/busqueda", tags=["busqueda"])

# --- Configuración ---------------------------------------------------------
# PROVISORIO: elegir el valor definitivo con `python -m scripts.evaluar`
# (mira el "margen" entre consultas correctas e irrelevantes).
UMBRAL_BUSQUEDA = 0.7
MAX_PROCEDIMIENTOS = 3
MAX_ESTUDIANTES = 20
LARGO_MINIMO_TEXTO = 4
LARGO_MAXIMO_TEXTO = 300

# Límite por usuario: cada consulta gasta cuota de la API de Gemini.
CONSULTAS_POR_VENTANA = 6
VENTANA_SEGUNDOS = 60


# --- Esquemas de entrada y salida -----------------------------------------
class ConsultaIn(BaseModel):
    texto: str = Field(..., max_length=LARGO_MAXIMO_TEXTO)
    # Solicitud activa del paciente: solo sirve para marcar a quién ya solicitó.
    solicitud_id: Optional[int] = None


class ProcedimientoOut(BaseModel):
    id: str
    nombre: str
    area: str
    area_nombre: str
    coincidencia: str  # "alta" | "media" | "baja" (el puntaje numérico no sale del servidor)


class BusquedaOut(BaseModel):
    procedimientos: List[ProcedimientoOut]
    area_sugerida: Optional[str] = None
    estudiantes: List[EstudianteOut]


# --- Límite de frecuencia (en memoria, suficiente para un solo servidor) ---
_historial: Dict[int, Deque[float]] = defaultdict(deque)
_candado = threading.Lock()


def verificar_limite(usuario_id: int, ahora: Optional[float] = None) -> None:
    """Lanza 429 si el usuario superó CONSULTAS_POR_VENTANA en VENTANA_SEGUNDOS."""
    ahora = time.monotonic() if ahora is None else ahora
    with _candado:
        marcas = _historial[usuario_id]
        while marcas and ahora - marcas[0] > VENTANA_SEGUNDOS:
            marcas.popleft()
        if len(marcas) >= CONSULTAS_POR_VENTANA:
            raise HTTPException(
                status_code=429,
                detail="Hiciste muchas consultas seguidas. Espera un minuto e inténtalo de nuevo.",
            )
        marcas.append(ahora)


# --- Lógica de estudiantes -------------------------------------------------
def estudiantes_con_cupo_en_areas(db: Session, areas: List[str], limite: int) -> List[models.Usuario]:
    """Estudiantes verificados con un requerimiento Abierto y cupos pendientes en `areas`.

    Se filtra en SQL (a diferencia de /api/estudiantes) y, a propósito, solo por
    requerimientos: tener un ramo en esa área no significa que necesite pacientes.
    """
    return (
        db.query(models.Usuario)
        .join(models.PerfilEstudiante, models.PerfilEstudiante.usuario_id == models.Usuario.id)
        .join(models.Requerimiento, models.Requerimiento.estudiante_id == models.Usuario.id)
        .filter(
            models.Usuario.rol == "estudiante",
            models.PerfilEstudiante.estado_verificacion == "Activo",
            models.Requerimiento.estado == "Abierto",
            models.Requerimiento.area.in_(areas),
            models.Requerimiento.cantidad_completada < models.Requerimiento.cantidad_requerida,
        )
        .distinct()
        .order_by(models.Usuario.id.desc())
        .limit(limite)
        .all()
    )


def ordenar_por_relevancia(estudiantes: List[EstudianteOut], areas: List[str]) -> List[EstudianteOut]:
    """Primero los que necesitan pacientes en el área del procedimiento más parecido.

    `areas` viene ordenada de más a menos relevante. Python mantiene el orden previo
    (más recientes primero) entre estudiantes con la misma relevancia.
    """

    def posicion(estudiante: EstudianteOut) -> int:
        posiciones = [
            areas.index(req.area) for req in estudiante.requerimientos_abiertos if req.area in areas
        ]
        return min(posiciones) if posiciones else len(areas)

    return sorted(estudiantes, key=posicion)


def areas_en_orden(coincidencias: List[dict]) -> List[str]:
    """Áreas sin repetir, conservando el orden de relevancia de los procedimientos."""
    areas: List[str] = []
    for coincidencia in coincidencias:
        if coincidencia["area"] not in areas:
            areas.append(coincidencia["area"])
    return areas


# --- Endpoint --------------------------------------------------------------
@router.post("", response_model=BusquedaOut)
def consultar(
    datos: ConsultaIn,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    texto = datos.texto.strip()
    if len(texto) < LARGO_MINIMO_TEXTO:
        raise HTTPException(status_code=422, detail="Escribe al menos unas palabras sobre lo que necesitas.")

    verificar_limite(usuario.id)
    estados = _estados_para_solicitud(db, usuario, datos.solicitud_id)

    try:
        coincidencias = buscar(texto, top_k=MAX_PROCEDIMIENTOS, umbral=UMBRAL_BUSQUEDA)
    except BuscadorNoDisponible:
        # logger.exception guarda el error técnico, pero nunca el texto del paciente.
        logger.exception("Falló la API de embeddings")
        raise HTTPException(
            status_code=503,
            detail="El buscador no está disponible por ahora. Puedes publicar tu solicitud igualmente.",
        )

    if not coincidencias:
        return BusquedaOut(procedimientos=[], area_sugerida=None, estudiantes=[])

    areas = areas_en_orden(coincidencias)
    procedimientos = [
        ProcedimientoOut(
            id=c["id"], nombre=c["nombre"], area=c["area"], area_nombre=AREAS[c["area"]],
            coincidencia=c["coincidencia"],
        )
        for c in coincidencias
    ]

    usuarios = estudiantes_con_cupo_en_areas(db, areas, MAX_ESTUDIANTES)
    ramos, reqs = _cargar(db, usuarios)
    estudiantes = [
        _out(e, ramos.get(e.id, []), reqs.get(e.id, []), estados.get(e.id)) for e in usuarios
    ]
    return BusquedaOut(
        procedimientos=procedimientos,
        area_sugerida=areas[0],
        estudiantes=ordenar_por_relevancia(estudiantes, areas),
    )
