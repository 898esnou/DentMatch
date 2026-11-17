"""
Estudiantes disponibles para el paciente:
- GET /api/estudiantes        (?area=, ?comuna=, ?turno=manana|tarde, ?solicitud_id=,
                               ?limit=, ?offset=)  -- solo estudiantes verificados
- GET /api/estudiantes/{id}
Del estudiante solo se muestra el nombre abreviado (nunca RUT ni correo).
Con ?solicitud_id=X, mi_postulacion_estado indica si ya lo solicité para esa solicitud.

Las funciones públicas de este módulo (consulta_estudiantes_visibles, cargar_ramos_y_requerimientos,
estudiante_out, estados_por_estudiante) también las usa la búsqueda semántica (busqueda.py).
"""
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Query as ConsultaSQL, Session, contains_eager

from app import models
from app.auth import require_rol
from app.catalogos import AREAS
from app.database import get_db
from app.sanciones import cuenta_activa
from app.schemas_dominio import EstudianteOut, RequerimientoResumen
from app.utils import ESCAPE_LIKE, nombre_corto, patron_contiene

router = APIRouter(prefix="/api/estudiantes", tags=["estudiantes"])

# Palabras que identifican el turno dentro del texto libre de disponibilidad.
TURNOS = {
    "manana": ("mañana", "manana", "a.m"),
    "tarde": ("tarde", "p.m"),
}


# ---------------------------------------------------------------- consultas compartidas
def consulta_estudiantes_visibles(db: Session) -> ConsultaSQL:
    """
    Estudiantes que un paciente puede ver: verificados ('Activo') y sin sanción vigente
    (los baneados o en time-out no aparecen). Trae el perfil en la misma consulta.
    """
    U, P, E = models.Usuario, models.PerfilEstudiante, models.EstadoCuenta
    return (
        db.query(U)
        .join(P, P.usuario_id == U.id)
        .outerjoin(E, E.usuario_id == U.id)
        .options(contains_eager(U.perfil_estudiante))
        .filter(
            U.rol == "estudiante",
            P.estado_verificacion == "Activo",
            or_(E.estado.is_(None), E.estado == "activo"),
        )
    )


def cargar_ramos_y_requerimientos(
    db: Session, estudiantes: List[models.Usuario]
) -> Tuple[Dict[int, list], Dict[int, list]]:
    """Ramos y requerimientos ABIERTOS de varios estudiantes, con 2 consultas en total."""
    ids = [e.id for e in estudiantes]
    if not ids:
        return {}, {}
    ramos: Dict[int, list] = {}
    for r in db.query(models.RamoEstudiante).filter(models.RamoEstudiante.estudiante_id.in_(ids)):
        ramos.setdefault(r.estudiante_id, []).append(r)
    requerimientos: Dict[int, list] = {}
    abiertos = db.query(models.Requerimiento).filter(
        models.Requerimiento.estudiante_id.in_(ids), models.Requerimiento.estado == "Abierto"
    )
    for r in abiertos:
        requerimientos.setdefault(r.estudiante_id, []).append(r)
    return ramos, requerimientos


def estudiante_out(
    e: models.Usuario, ramos: list, requerimientos: list, mi_estado: Optional[str]
) -> EstudianteOut:
    """Ficha pública del estudiante (lo que ve el paciente)."""
    perfil = e.perfil_estudiante
    areas = sorted({r.area for r in ramos} | {r.area for r in requerimientos})
    tutores = sorted({t for t in [r.tutor for r in ramos] + [r.tutor for r in requerimientos] if t})
    return EstudianteOut(
        id=e.id,
        nombre=nombre_corto(e.nombre_completo),
        universidad=perfil.universidad,
        ano_carrera=perfil.ano_carrera,
        comuna_atencion=perfil.comuna_atencion,
        disponibilidad=perfil.disponibilidad,
        estado_verificacion=perfil.estado_verificacion,
        areas=areas,
        tutores=tutores,
        ramos=sorted({r.ramo for r in ramos}),
        requerimientos_abiertos=[
            RequerimientoResumen(
                id=r.id, tratamiento=r.tratamiento, area=r.area, tutor=r.tutor,
                restantes=max(r.cantidad_requerida - r.cantidad_completada, 0),
            )
            for r in requerimientos
        ],
        mi_postulacion_estado=mi_estado,
    )


def estados_por_estudiante(db: Session, usuario: models.Usuario, solicitud_id: Optional[int]) -> dict:
    """
    {estudiante_id: estado de la postulación} para una solicitud del paciente, así cada ficha
    sabe si ya se le pidió atención. 404 si la solicitud no es de este paciente.
    """
    if solicitud_id is None:
        return {}
    s = db.get(models.Solicitud, solicitud_id)
    if s is None or s.paciente_id != usuario.id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {p.estudiante_id: p.estado for p in s.postulaciones}


# ---------------------------------------------------------------- endpoints
@router.get("", response_model=List[EstudianteOut])
def listar_estudiantes(
    area: Optional[str] = Query(None),
    comuna: Optional[str] = Query(None),
    turno: Optional[str] = Query(None, pattern="^(manana|tarde)$"),
    solicitud_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    if area is not None and area not in AREAS:
        raise HTTPException(status_code=422, detail="Área inválida")
    estados = estados_por_estudiante(db, usuario, solicitud_id)

    P = models.PerfilEstudiante
    consulta = consulta_estudiantes_visibles(db)
    if comuna and comuna.strip():
        consulta = consulta.filter(P.comuna_atencion.ilike(patron_contiene(comuna), escape=ESCAPE_LIKE))
    if turno:
        consulta = consulta.filter(or_(*(P.disponibilidad.ilike(f"%{palabra}%") for palabra in TURNOS[turno])))
    estudiantes = consulta.order_by(models.Usuario.id.desc()).all()

    ramos, requerimientos = cargar_ramos_y_requerimientos(db, estudiantes)
    salida = [
        estudiante_out(e, ramos.get(e.id, []), requerimientos.get(e.id, []), estados.get(e.id))
        for e in estudiantes
    ]
    # El área sale de los ramos y requerimientos del estudiante, por eso se filtra aquí y no en SQL.
    if area:
        salida = [e for e in salida if area in e.areas]
    return salida[offset : offset + limit]


@router.get("/{estudiante_id}", response_model=EstudianteOut)
def ver_estudiante(
    estudiante_id: int,
    solicitud_id: Optional[int] = Query(None),
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    e = db.get(models.Usuario, estudiante_id)
    if (
        e is None or e.rol != "estudiante" or e.perfil_estudiante is None
        or e.perfil_estudiante.estado_verificacion != "Activo"
        or not cuenta_activa(db, e.id)
    ):
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    estados = estados_por_estudiante(db, usuario, solicitud_id)
    ramos, requerimientos = cargar_ramos_y_requerimientos(db, [e])
    return estudiante_out(e, ramos.get(e.id, []), requerimientos.get(e.id, []), estados.get(e.id))
