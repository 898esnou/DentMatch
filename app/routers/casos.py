"""
Casos clínicos disponibles para el estudiante (solicitudes abiertas de pacientes):
- GET /api/casos        (?area=, ?urgente=, ?comuna=, ?q=, ?limit=, ?offset=)
- GET /api/casos/{id}
Del paciente solo se muestra el nombre abreviado.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.catalogos import AREAS
from app.database import get_db
from app.schemas_dominio import CasoOut
from app.utils import nombre_corto

router = APIRouter(prefix="/api/casos", tags=["casos"])


def _caso_out(s: models.Solicitud, mi_postulacion: Optional[models.Postulacion]) -> CasoOut:
    return CasoOut(
        id=s.id,
        codigo=s.codigo,
        titulo=s.titulo,
        descripcion=s.descripcion,
        area=s.area,
        area_nombre=AREAS.get(s.area, s.area),
        urgente=s.urgente,
        comuna=s.comuna,
        disponibilidad=s.disponibilidad,
        paciente=nombre_corto(s.paciente.nombre_completo),
        estado=s.estado_api,
        fecha_creacion=s.fecha_creacion,
        mi_postulacion_id=mi_postulacion.id if mi_postulacion else None,
        mi_postulacion_estado=mi_postulacion.estado if mi_postulacion else None,
    )


def _mis_postulaciones(db: Session, usuario: models.Usuario, solicitud_ids: List[int]) -> dict:
    if not solicitud_ids:
        return {}
    filas = (
        db.query(models.Postulacion)
        .filter(
            models.Postulacion.estudiante_id == usuario.id,
            models.Postulacion.solicitud_id.in_(solicitud_ids),
        )
        .all()
    )
    return {p.solicitud_id: p for p in filas}


@router.get("", response_model=List[CasoOut])
def listar_casos(
    area: Optional[str] = Query(None),
    urgente: Optional[bool] = Query(None),
    comuna: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Texto a buscar en título y descripción"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    if area is not None and area not in AREAS:
        raise HTTPException(status_code=422, detail="Área inválida")
    D = models.SolicitudDetalle
    # Solo las que el equipo tiene en 'Buscando'. El detalle puede faltar (filas creadas
    # por otra app): en ese caso cuenta como área 'diagnostico' y no urgente.
    consulta = (
        db.query(models.Solicitud)
        .outerjoin(D, D.solicitud_id == models.Solicitud.id)
        .filter(models.Solicitud.estado == "Buscando")
    )
    area_efectiva = func.coalesce(D.area, "diagnostico")
    urgente_efectivo = func.coalesce(D.urgente, False)
    if area:
        consulta = consulta.filter(area_efectiva == area)
    if urgente is not None:
        consulta = consulta.filter(urgente_efectivo == urgente)
    if comuna:
        consulta = consulta.filter(models.Solicitud.comuna.ilike(f"%{comuna}%"))
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(D.titulo.ilike(patron) | models.Solicitud.descripcion.ilike(patron))
    # Primero las urgentes y, dentro de cada grupo, las más recientes.
    filas = (
        consulta.order_by(urgente_efectivo.desc(), models.Solicitud.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    mias = _mis_postulaciones(db, usuario, [s.id for s in filas])
    return [_caso_out(s, mias.get(s.id)) for s in filas]


@router.get("/{caso_id}", response_model=CasoOut)
def ver_caso(
    caso_id: int,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    s = db.get(models.Solicitud, caso_id)
    mia = _mis_postulaciones(db, usuario, [caso_id]).get(caso_id)
    # Solo se ve si sigue abierta o si el estudiante ya tiene que ver con ella.
    if s is None or (not s.abierta and mia is None):
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return _caso_out(s, mia)
