"""
Reglas de negocio compartidas entre routers (para que no se dupliquen).
"""
from datetime import datetime
from typing import Dict, Iterable, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app import models


def recalcular_estado_solicitud(solicitud: models.Solicitud) -> None:
    """
    Deja el estado de la tabla del equipo coherente con las postulaciones:
    alguna Aceptada -> 'Asignado'; si no -> 'Buscando'.
    (Abierta / En Revisión se derivan solas: ver Solicitud.estado_api.)
    No toca las solicitudes Canceladas ni las ya Completadas.
    """
    if solicitud.estado == "Cancelado":
        return
    if solicitud.detalle is not None and solicitud.detalle.completada_en is not None:
        return
    hay_aceptada = any(p.estado == "Aceptada" for p in solicitud.postulaciones)
    solicitud.estado = "Asignado" if hay_aceptada else "Buscando"


def asegurar_detalle(solicitud: models.Solicitud) -> models.SolicitudDetalle:
    """Las solicitudes creadas por otra app no tienen fila de detalle: se crea al necesitarla."""
    if solicitud.detalle is None:
        solicitud.detalle = models.SolicitudDetalle(area="diagnostico", urgente=False)
    return solicitud.detalle


def contar_postulaciones(db: Session, solicitud_ids: Iterable[int]) -> Dict[int, Tuple[int, int]]:
    """{solicitud_id: (total, pendientes)} en una sola consulta."""
    ids = list(solicitud_ids)
    if not ids:
        return {}
    filas = (
        db.query(
            models.Postulacion.solicitud_id,
            func.count(models.Postulacion.id),
            func.sum(case((models.Postulacion.estado == "Pendiente", 1), else_=0)),
        )
        .filter(
            models.Postulacion.solicitud_id.in_(ids),
            models.Postulacion.estado != "Cancelada",
        )
        .group_by(models.Postulacion.solicitud_id)
        .all()
    )
    return {sid: (int(total), int(pend or 0)) for sid, total, pend in filas}


def ahora() -> datetime:
    """Hora actual sin zona horaria (así se guardan los TIMESTAMP)."""
    return datetime.now()
