"""
Estudiantes disponibles para el paciente:
- GET /api/estudiantes        (?area=, ?comuna=, ?turno=manana|tarde, ?solicitud_id=,
                               ?solo_verificados=, ?limit=, ?offset=)
- GET /api/estudiantes/{id}
Del estudiante solo se muestra el nombre abreviado (nunca RUT ni correo).
Con ?solicitud_id=X, mi_postulacion_estado indica si ya lo solicité para esa solicitud.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.catalogos import AREAS
from app.database import get_db
from app.schemas_dominio import EstudianteOut, RequerimientoResumen
from app.utils import nombre_corto

router = APIRouter(prefix="/api/estudiantes", tags=["estudiantes"])

# Palabras que identifican el turno dentro del texto libre de disponibilidad.
TURNOS = {
    "manana": ("mañana", "manana", "a.m"),
    "tarde": ("tarde", "p.m"),
}


def _cargar(db: Session, estudiantes: List[models.Usuario]):
    ids = [e.id for e in estudiantes]
    if not ids:
        return {}, {}
    ramos: Dict[int, list] = {}
    for r in db.query(models.RamoEstudiante).filter(models.RamoEstudiante.estudiante_id.in_(ids)):
        ramos.setdefault(r.estudiante_id, []).append(r)
    reqs: Dict[int, list] = {}
    abiertos = db.query(models.Requerimiento).filter(
        models.Requerimiento.estudiante_id.in_(ids), models.Requerimiento.estado == "Abierto"
    )
    for r in abiertos:
        reqs.setdefault(r.estudiante_id, []).append(r)
    return ramos, reqs


def _out(e: models.Usuario, ramos: list, reqs: list, mi_estado: Optional[str]) -> EstudianteOut:
    perfil = e.perfil_estudiante
    areas = sorted({r.area for r in ramos} | {r.area for r in reqs})
    tutores = sorted({t for t in [r.tutor for r in ramos] + [r.tutor for r in reqs] if t})
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
            for r in reqs
        ],
        mi_postulacion_estado=mi_estado,
    )


def _estados_para_solicitud(db: Session, usuario: models.Usuario, solicitud_id: Optional[int]) -> dict:
    if solicitud_id is None:
        return {}
    s = db.get(models.Solicitud, solicitud_id)
    if s is None or s.paciente_id != usuario.id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {p.estudiante_id: p.estado for p in s.postulaciones}


@router.get("", response_model=List[EstudianteOut])
def listar_estudiantes(
    area: Optional[str] = Query(None),
    comuna: Optional[str] = Query(None),
    turno: Optional[str] = Query(None, pattern="^(manana|tarde)$"),
    solicitud_id: Optional[int] = Query(None),
    solo_verificados: bool = Query(False, description="Solo estudiantes con estado 'Activo'"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    if area is not None and area not in AREAS:
        raise HTTPException(status_code=422, detail="Área inválida")
    estados = _estados_para_solicitud(db, usuario, solicitud_id)

    consulta = (
        db.query(models.Usuario)
        .join(models.PerfilEstudiante, models.PerfilEstudiante.usuario_id == models.Usuario.id)
        .filter(models.Usuario.rol == "estudiante")
    )
    if solo_verificados:
        consulta = consulta.filter(models.PerfilEstudiante.estado_verificacion == "Activo")
    if comuna:
        consulta = consulta.filter(models.PerfilEstudiante.comuna_atencion.ilike(f"%{comuna}%"))
    if turno:
        condicion = None
        for palabra in TURNOS[turno]:
            c = models.PerfilEstudiante.disponibilidad.ilike(f"%{palabra}%")
            condicion = c if condicion is None else condicion | c
        consulta = consulta.filter(condicion)
    estudiantes = consulta.order_by(models.Usuario.id.desc()).all()

    ramos, reqs = _cargar(db, estudiantes)
    salida = [
        _out(e, ramos.get(e.id, []), reqs.get(e.id, []), estados.get(e.id)) for e in estudiantes
    ]
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
    if e is None or e.rol != "estudiante" or e.perfil_estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    estados = _estados_para_solicitud(db, usuario, solicitud_id)
    ramos, reqs = _cargar(db, [e])
    return _out(e, ramos.get(e.id, []), reqs.get(e.id, []), estados.get(e.id))
