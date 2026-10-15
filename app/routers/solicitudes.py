"""
Solicitudes clínicas del paciente:
- POST  /api/solicitudes                 publicar una necesidad de atención
- GET   /api/solicitudes                 las mías (?estado=...)
- GET   /api/solicitudes/{id}
- PATCH /api/solicitudes/{id}            editar (solo Abierta / En Revisión)
- POST  /api/solicitudes/{id}/cancelar
Solo pacientes, y cada uno ve únicamente las suyas. Los estudiantes ven las
solicitudes abiertas por /api/casos.

La tabla `solicitudes` es del equipo: usamos sus columnas tal cual y guardamos
lo demás en `solicitud_detalle` (ver app/models.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.catalogos import AREAS, ESTADOS_SOLICITUD
from app.database import get_db
from app.schemas_dominio import SolicitudIn, SolicitudOut, SolicitudUpdate
from app.servicios import ahora, asegurar_detalle, contar_postulaciones

router = APIRouter(prefix="/api/solicitudes", tags=["solicitudes"])

SIN_COMUNA = "Sin especificar"  # la tabla del equipo exige comuna_paciente (NOT NULL)


def solicitud_out(s: models.Solicitud, total: int = 0, pendientes: int = 0) -> SolicitudOut:
    return SolicitudOut(
        id=s.id,
        codigo=s.codigo,
        titulo=s.titulo,
        descripcion=s.descripcion,
        area=s.area,
        area_nombre=AREAS.get(s.area, s.area),
        urgente=s.urgente,
        comuna=None if s.comuna == SIN_COMUNA else s.comuna,
        distancia_max_km=s.distancia_max_km,
        disponibilidad=s.disponibilidad,
        preferencia=s.preferencia,
        estado=s.estado_api,
        fecha_creacion=s.fecha_creacion,
        total_postulaciones=total,
        postulaciones_pendientes=pendientes,
    )


def _propia(db: Session, solicitud_id: int, usuario: models.Usuario) -> models.Solicitud:
    s = db.get(models.Solicitud, solicitud_id)
    if s is None or s.paciente_id != usuario.id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return s


def _out_con_conteo(db: Session, s: models.Solicitud) -> SolicitudOut:
    total, pendientes = contar_postulaciones(db, [s.id]).get(s.id, (0, 0))
    return solicitud_out(s, total, pendientes)


@router.post("", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED)
def crear_solicitud(
    datos: SolicitudIn,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    comuna = datos.comuna
    # Si no indica comuna, usamos la de su perfil.
    if not comuna and usuario.perfil_paciente and usuario.perfil_paciente.comuna:
        comuna = usuario.perfil_paciente.comuna
    s = models.Solicitud(
        paciente_id=usuario.id,
        descripcion=datos.descripcion,
        comuna=comuna or SIN_COMUNA,
        estado="Buscando",
        detalle=models.SolicitudDetalle(
            titulo=datos.titulo,
            area=datos.area,
            urgente=datos.urgente,
            distancia_max_km=datos.distancia_max_km,
            disponibilidad=datos.disponibilidad,
            preferencia=datos.preferencia,
        ),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return solicitud_out(s)


@router.get("", response_model=List[SolicitudOut])
def listar_mis_solicitudes(
    estado: Optional[str] = Query(None),
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_SOLICITUD:
        raise HTTPException(status_code=422, detail="Estado inválido")
    filas = (
        db.query(models.Solicitud)
        .filter(models.Solicitud.paciente_id == usuario.id)
        .order_by(models.Solicitud.id.desc())
        .all()
    )
    if estado:  # el estado de la API se deriva, así que se filtra aquí
        filas = [s for s in filas if s.estado_api == estado]
    conteos = contar_postulaciones(db, [s.id for s in filas])
    return [solicitud_out(s, *conteos.get(s.id, (0, 0))) for s in filas]


@router.get("/{solicitud_id}", response_model=SolicitudOut)
def ver_solicitud(
    solicitud_id: int,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    return _out_con_conteo(db, _propia(db, solicitud_id, usuario))


@router.patch("/{solicitud_id}", response_model=SolicitudOut)
def editar_solicitud(
    solicitud_id: int,
    datos: SolicitudUpdate,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    s = _propia(db, solicitud_id, usuario)
    if not s.abierta:
        raise HTTPException(status_code=409, detail=f"No se puede editar una solicitud {s.estado_api.lower()}")
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("titulo", "descripcion", "area", "urgente"):
        if campo in cambios and cambios[campo] is None:
            raise HTTPException(status_code=422, detail=f"'{campo}' no puede quedar vacío")

    if "descripcion" in cambios:
        s.descripcion = cambios.pop("descripcion")
    if "comuna" in cambios:
        s.comuna = cambios.pop("comuna") or SIN_COMUNA
    detalle = asegurar_detalle(s)
    for campo, valor in cambios.items():
        setattr(detalle, campo, valor)
    db.commit()
    db.refresh(s)
    return _out_con_conteo(db, s)


@router.post("/{solicitud_id}/cancelar", response_model=SolicitudOut)
def cancelar_solicitud(
    solicitud_id: int,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    s = _propia(db, solicitud_id, usuario)
    if s.estado_api in ("Completada", "Cancelada"):
        raise HTTPException(status_code=409, detail=f"La solicitud ya está {s.estado_api.lower()}")
    s.estado = "Cancelado"
    # Se cancela todo lo que estaba en curso con esta solicitud.
    for p in s.postulaciones:
        if p.estado in ("Pendiente", "Aceptada"):
            p.estado = "Cancelada"
            p.fecha_respuesta = ahora()
            for c in p.citas:
                if c.estado == "Agendada":
                    c.estado = "Cancelada"
    db.commit()
    db.refresh(s)
    return _out_con_conteo(db, s)
