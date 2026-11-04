"""
Búsqueda semántica para el paciente ("Haz tu consulta"):
- POST /api/busqueda                   {"texto": "...", "solicitud_id": opcional, "pagina": 1}
- POST /api/busqueda/retroalimentacion {"util": true, "procedimiento_id": opcional, "coincidencia": opcional}
- GET  /api/busqueda/estadisticas      (solo admin) qué tan útiles resultaron las sugerencias

Relaciona lo que escribe el paciente con procedimientos del catálogo
(app/datos/procedimientos.json) y devuelve:
  1. los procedimientos relacionados (con su área y la frase del catálogo que coincidió),
  2. los estudiantes verificados con un requerimiento ABIERTO y cupos pendientes en esas
     áreas, ordenados por un puntaje de coincidencia (procedimiento, ubicación y
     disponibilidad, ver app/matching.py) y paginados de a 10,
  3. un mensaje cuando la coincidencia es débil o no existe, y un aviso de posible
     urgencia (ver app/urgencia.py) cuando el texto menciona señales de alarma.

NO diagnostica ni recomienda tratamientos: solo conecta palabras con el catálogo.
El texto del paciente no se guarda ni se escribe en los logs.
"""
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.busqueda_semantica import BuscadorNoDisponible, buscar, cargar_catalogo
from app.catalogos import AREAS
from app.database import get_db
from app.matching import (
    POR_PAGINA,
    calcular_puntaje,
    motivos_de_coincidencia,
    paginar,
    puntaje_disponibilidad,
    puntaje_procedimiento,
    puntaje_ubicacion,
)
from app.routers.estudiantes import _cargar, _estados_para_solicitud, _out
from app.schemas_dominio import EstudianteOut
from app.urgencia import MENSAJE_URGENCIA, detectar_urgencia

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/busqueda", tags=["busqueda"])

# --- Configuración ---------------------------------------------------------
# Calibrado con `python -m scripts.evaluar` (143 frases, 27 consultas correctas y 6 irrelevantes):
# las correctas puntúan >= 0.816 y las irrelevantes <= 0.668. 0.75 queda entre ambos grupos.
# Volver a calibrar si se agregan procedimientos o frases.
UMBRAL_BUSQUEDA = 0.75
MAX_PROCEDIMIENTOS = 3
MAX_CANDIDATOS = 200  # estudiantes que se puntúan antes de paginar
LARGO_MINIMO_TEXTO = 4
LARGO_MAXIMO_TEXTO = 300

# Límite por usuario: cada consulta gasta cuota de la API de Gemini.
CONSULTAS_POR_VENTANA = 6
OPINIONES_POR_VENTANA = 20
VENTANA_SEGUNDOS = 60

MENSAJE_SIN_COINCIDENCIA = (
    "No encontramos un procedimiento claramente parecido a lo que describes. Puedes probar con "
    "otras palabras o publicar tu solicitud igualmente, y explicarle estos mismos síntomas al "
    "estudiante que te atienda para ver si corresponden a lo que él trata."
)
MENSAJE_COINCIDENCIA_MEDIA = (
    "Estas son recomendaciones cercanas a lo que describes, pero no estamos seguros de que sean lo "
    "que necesitas. Te recomendamos explicarle estos mismos síntomas al estudiante que te atenderá, "
    "para ver si son acordes a lo que él trata."
)


# --- Esquemas de entrada y salida -----------------------------------------
class ConsultaIn(BaseModel):
    texto: str = Field(..., max_length=LARGO_MAXIMO_TEXTO)
    # Solicitud activa del paciente: sirve para marcar a quién ya solicitó y para usar su
    # comuna y disponibilidad al calcular el puntaje de coincidencia.
    solicitud_id: Optional[int] = None
    pagina: int = Field(1, ge=1, le=50)


class ProcedimientoOut(BaseModel):
    id: str
    nombre: str
    area: str
    area_nombre: str
    coincidencia: str  # "alta" | "media" | "baja" (el puntaje numérico no sale del servidor)
    coincide_con: Optional[str] = None  # frase del catálogo que más se pareció a lo escrito


class EstudianteCoincidenciaOut(EstudianteOut):
    puntaje: int = 0  # 0 a 100, ver app/matching.py
    motivos: List[str] = []


class BusquedaOut(BaseModel):
    procedimientos: List[ProcedimientoOut]
    area_sugerida: Optional[str] = None
    estudiantes: List[EstudianteCoincidenciaOut]
    mensaje: Optional[str] = None
    aviso_urgencia: Optional[str] = None
    pagina: int = 1
    paginas: int = 1
    total_estudiantes: int = 0


class RetroalimentacionIn(BaseModel):
    util: bool
    procedimiento_id: Optional[str] = Field(None, max_length=50)
    coincidencia: Optional[Literal["alta", "media", "baja"]] = None


class EstadisticaOpinionOut(BaseModel):
    procedimiento_id: Optional[str] = None
    nombre: Optional[str] = None
    total: int
    utiles: int
    no_utiles: int
    porcentaje_utiles: int


# --- Límite de frecuencia (en memoria, suficiente para un solo servidor) ---
_historial: Dict[int, Deque[float]] = defaultdict(deque)
_historial_opiniones: Dict[int, Deque[float]] = defaultdict(deque)
_candado = threading.Lock()


def verificar_limite(
    usuario_id: int,
    ahora: Optional[float] = None,
    historial: Optional[Dict[int, Deque[float]]] = None,
    maximo: int = CONSULTAS_POR_VENTANA,
) -> None:
    """Lanza 429 si el usuario superó `maximo` solicitudes en VENTANA_SEGUNDOS."""
    historial = _historial if historial is None else historial
    ahora = time.monotonic() if ahora is None else ahora
    with _candado:
        marcas = historial[usuario_id]
        while marcas and ahora - marcas[0] > VENTANA_SEGUNDOS:
            marcas.popleft()
        if len(marcas) >= maximo:
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


def areas_en_orden(coincidencias: List[dict]) -> List[str]:
    """Áreas sin repetir, conservando el orden de relevancia de los procedimientos."""
    areas: List[str] = []
    for coincidencia in coincidencias:
        if coincidencia["area"] not in areas:
            areas.append(coincidencia["area"])
    return areas


def datos_del_paciente(
    db: Session, usuario: models.Usuario, solicitud_id: Optional[int]
) -> Tuple[Optional[str], Optional[str]]:
    """(comuna, disponibilidad) del paciente: primero los de su solicitud activa, si no los de su perfil."""
    comuna = disponibilidad = None
    if solicitud_id is not None:
        solicitud = db.get(models.Solicitud, solicitud_id)  # ya se validó que sea suya
        if solicitud is not None:
            comuna = solicitud.comuna
            disponibilidad = solicitud.disponibilidad
    perfil = usuario.perfil_paciente
    if perfil is not None:
        comuna = comuna or perfil.comuna
        disponibilidad = disponibilidad or perfil.disponibilidad
    return comuna, disponibilidad


def clasificar_estudiantes(
    estudiantes: List[EstudianteOut],
    coincidencias: List[dict],
    comuna: Optional[str],
    disponibilidad: Optional[str],
) -> List[EstudianteCoincidenciaOut]:
    """Asigna a cada estudiante su puntaje de coincidencia y los ordena de mayor a menor.

    Procedimiento: se toma el área de sus requerimientos abiertos más parecida a la consulta.
    En caso de empate gana el estudiante más reciente.
    """
    similitud_por_area: Dict[str, float] = {}
    for c in coincidencias:
        similitud_por_area[c["area"]] = max(similitud_por_area.get(c["area"], 0.0), c["puntaje"])

    resultado = []
    for e in estudiantes:
        areas_del_estudiante = [r.area for r in e.requerimientos_abiertos if r.area in similitud_por_area]
        mejor_area = max(areas_del_estudiante, key=lambda a: similitud_por_area[a]) if areas_del_estudiante else None
        procedimiento = puntaje_procedimiento(similitud_por_area[mejor_area], UMBRAL_BUSQUEDA) if mejor_area else 0.0
        ubicacion = puntaje_ubicacion(comuna, e.comuna_atencion)
        horario = puntaje_disponibilidad(disponibilidad, e.disponibilidad)
        resultado.append(
            EstudianteCoincidenciaOut(
                **e.model_dump(),
                puntaje=calcular_puntaje(procedimiento, ubicacion, horario),
                motivos=motivos_de_coincidencia(AREAS.get(mejor_area), ubicacion, horario),
            )
        )
    resultado.sort(key=lambda e: (-e.puntaje, -e.id))
    return resultado


# --- Endpoints -------------------------------------------------------------
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
    aviso_urgencia = MENSAJE_URGENCIA if detectar_urgencia(texto) else None

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
        return BusquedaOut(
            procedimientos=[], area_sugerida=None, estudiantes=[],
            mensaje=MENSAJE_SIN_COINCIDENCIA, aviso_urgencia=aviso_urgencia,
        )

    areas = areas_en_orden(coincidencias)
    procedimientos = [
        ProcedimientoOut(
            id=c["id"], nombre=c["nombre"], area=c["area"], area_nombre=AREAS[c["area"]],
            coincidencia=c["coincidencia"], coincide_con=c.get("frase"),
        )
        for c in coincidencias
    ]

    usuarios = estudiantes_con_cupo_en_areas(db, areas, MAX_CANDIDATOS)
    ramos, reqs = _cargar(db, usuarios)
    estudiantes = [
        _out(e, ramos.get(e.id, []), reqs.get(e.id, []), estados.get(e.id)) for e in usuarios
    ]
    comuna, disponibilidad = datos_del_paciente(db, usuario, datos.solicitud_id)
    ordenados = clasificar_estudiantes(estudiantes, coincidencias, comuna, disponibilidad)
    de_la_pagina, total_paginas = paginar(ordenados, datos.pagina, POR_PAGINA)

    return BusquedaOut(
        procedimientos=procedimientos,
        area_sugerida=areas[0],
        estudiantes=de_la_pagina,
        mensaje=MENSAJE_COINCIDENCIA_MEDIA if coincidencias[0]["coincidencia"] != "alta" else None,
        aviso_urgencia=aviso_urgencia,
        pagina=min(datos.pagina, total_paginas),
        paginas=total_paginas,
        total_estudiantes=len(ordenados),
    )


@router.post("/retroalimentacion", status_code=status.HTTP_201_CREATED)
def registrar_retroalimentacion(
    datos: RetroalimentacionIn,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    """Guarda si una sugerencia fue útil. Es anónima: no se registra quién opinó ni qué escribió."""
    verificar_limite(usuario.id, historial=_historial_opiniones, maximo=OPINIONES_POR_VENTANA)
    if datos.procedimiento_id is not None:
        ids_validos = {p["id"] for p in cargar_catalogo()[0]}
        if datos.procedimiento_id not in ids_validos:
            raise HTTPException(status_code=422, detail="Procedimiento desconocido.")
    db.add(
        models.RetroalimentacionBusqueda(
            procedimiento_id=datos.procedimiento_id, coincidencia=datos.coincidencia, util=datos.util
        )
    )
    db.commit()
    return {"detail": "Gracias por tu opinión."}


@router.get("/estadisticas", response_model=List[EstadisticaOpinionOut])
def estadisticas_de_opiniones(
    _: models.Usuario = Depends(require_rol("admin")),
    db: Session = Depends(get_db),
):
    """Cuántas veces se opinó sobre cada procedimiento sugerido y qué porcentaje fue útil."""
    R = models.RetroalimentacionBusqueda
    filas = (
        db.query(R.procedimiento_id, func.count(R.id), func.sum(case((R.util.is_(True), 1), else_=0)))
        .group_by(R.procedimiento_id)
        .all()
    )
    nombres = {p["id"]: p["nombre_profesional"] for p in cargar_catalogo()[0]}
    salida = []
    for procedimiento_id, total, utiles in filas:
        utiles = int(utiles or 0)
        salida.append(
            EstadisticaOpinionOut(
                procedimiento_id=procedimiento_id,
                nombre=nombres.get(procedimiento_id) if procedimiento_id else "Sin coincidencia",
                total=int(total),
                utiles=utiles,
                no_utiles=int(total) - utiles,
                porcentaje_utiles=round(100 * utiles / int(total)),
            )
        )
    return sorted(salida, key=lambda s: s.total, reverse=True)
