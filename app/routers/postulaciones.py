"""
Postulaciones: el vínculo entre una solicitud (paciente) y un estudiante.
Las puede iniciar cualquiera de los dos y las responde la contraparte.

- POST /api/postulaciones                  iniciar
    · estudiante: {solicitud_id, requerimiento_id?, mensaje?}  ("Postular a caso")
    · paciente:   {solicitud_id, estudiante_id, requerimiento_id?, mensaje?}  ("Solicitar")
- GET  /api/postulaciones                  las mías (?estado, ?solicitud_id, ?tipo=recibidas|enviadas)
- GET  /api/postulaciones/{id}
- POST /api/postulaciones/{id}/responder   {accion: aceptar|rechazar}  (solo la contraparte)
- POST /api/postulaciones/{id}/cancelar    (quien la inició si está Pendiente; cualquiera si está Aceptada)
- POST /api/postulaciones/{id}/completar   (estudiante) el tratamiento se realizó
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app import models
from app.auth import require_rol
from app.catalogos import ESTADOS_POSTULACION
from app.database import get_db
from app.routers.requerimientos import marcar_completado_si_corresponde
from app.schemas_dominio import (
    ParticipanteOut, PostulacionIn, PostulacionOut, RequerimientoResumen, RespuestaIn,
    SolicitudResumen,
)
from app.servicios import ahora, asegurar_detalle, recalcular_estado_solicitud
from app.utils import nombre_corto

router = APIRouter(prefix="/api/postulaciones", tags=["postulaciones"])

ambos_roles = require_rol("estudiante", "paciente")


def postulacion_out(p: models.Postulacion, usuario: models.Usuario) -> PostulacionOut:
    s = p.solicitud
    r = p.requerimiento
    return PostulacionOut(
        id=p.id,
        solicitud=SolicitudResumen(
            id=s.id, codigo=s.codigo, titulo=s.titulo, area=s.area, estado=s.estado_api, comuna=s.comuna
        ),
        estudiante=ParticipanteOut(id=p.estudiante_id, nombre=nombre_corto(p.estudiante.nombre_completo)),
        paciente=ParticipanteOut(id=s.paciente_id, nombre=nombre_corto(s.paciente.nombre_completo)),
        requerimiento=RequerimientoResumen(
            id=r.id, tratamiento=r.tratamiento, area=r.area, tutor=r.tutor,
            restantes=max(r.cantidad_requerida - r.cantidad_completada, 0),
        ) if r else None,
        iniciada_por=p.iniciada_por,
        estado=p.estado,
        mensaje=p.mensaje,
        fecha_creacion=p.fecha_creacion,
        fecha_respuesta=p.fecha_respuesta,
        puede_responder=p.estado == "Pendiente" and p.iniciada_por != usuario.rol,
    )


def _consulta_base(db: Session):
    return db.query(models.Postulacion).options(
        joinedload(models.Postulacion.solicitud).joinedload(models.Solicitud.paciente),
        joinedload(models.Postulacion.estudiante),
        joinedload(models.Postulacion.requerimiento),
    )


def _es_participante(p: models.Postulacion, usuario: models.Usuario) -> bool:
    if usuario.rol == "estudiante":
        return p.estudiante_id == usuario.id
    return p.solicitud.paciente_id == usuario.id


def _visible(db: Session, postulacion_id: int, usuario: models.Usuario) -> models.Postulacion:
    p = _consulta_base(db).filter(models.Postulacion.id == postulacion_id).first()
    if p is None or not _es_participante(p, usuario):
        raise HTTPException(status_code=404, detail="Postulación no encontrada")
    return p


@router.post("", response_model=PostulacionOut, status_code=status.HTTP_201_CREATED)
def iniciar_postulacion(
    datos: PostulacionIn,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    solicitud = db.get(models.Solicitud, datos.solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if usuario.rol == "estudiante":
        estudiante = usuario
    else:
        if solicitud.paciente_id != usuario.id:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        if datos.estudiante_id is None:
            raise HTTPException(status_code=422, detail="Indica a qué estudiante quieres solicitar")
        estudiante = db.get(models.Usuario, datos.estudiante_id)
        if estudiante is None or estudiante.rol != "estudiante" or estudiante.perfil_estudiante is None:
            raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if not solicitud.abierta:
        raise HTTPException(status_code=409, detail=f"La solicitud está {solicitud.estado_api.lower()}")

    if datos.requerimiento_id is not None:
        req = db.get(models.Requerimiento, datos.requerimiento_id)
        if req is None or req.estudiante_id != estudiante.id:
            raise HTTPException(status_code=404, detail="Requerimiento no encontrado")
        if req.estado != "Abierto":
            raise HTTPException(status_code=409, detail=f"El requerimiento está {req.estado.lower()}")

    existente = (
        db.query(models.Postulacion)
        .filter(
            models.Postulacion.solicitud_id == solicitud.id,
            models.Postulacion.estudiante_id == estudiante.id,
        )
        .first()
    )
    if existente is not None and existente.estado != "Cancelada":
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una postulación entre esta solicitud y este estudiante ({existente.estado.lower()})",
        )

    if existente is not None:  # estaba cancelada: se reabre
        p = existente
        p.estado = "Pendiente"
        p.fecha_respuesta = None
    else:
        p = models.Postulacion(solicitud_id=solicitud.id, estudiante_id=estudiante.id)
        db.add(p)
    p.iniciada_por = usuario.rol
    p.requerimiento_id = datos.requerimiento_id
    p.mensaje = datos.mensaje
    db.flush()
    db.refresh(solicitud)
    recalcular_estado_solicitud(solicitud)
    db.commit()
    return postulacion_out(_visible(db, p.id, usuario), usuario)


@router.get("", response_model=List[PostulacionOut])
def listar_postulaciones(
    estado: Optional[str] = Query(None),
    solicitud_id: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None, pattern="^(recibidas|enviadas)$"),
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_POSTULACION:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = _consulta_base(db)
    if usuario.rol == "estudiante":
        consulta = consulta.filter(models.Postulacion.estudiante_id == usuario.id)
    else:
        consulta = consulta.join(models.Solicitud, models.Postulacion.solicitud_id == models.Solicitud.id)
        consulta = consulta.filter(models.Solicitud.paciente_id == usuario.id)
    if estado:
        consulta = consulta.filter(models.Postulacion.estado == estado)
    if solicitud_id is not None:
        consulta = consulta.filter(models.Postulacion.solicitud_id == solicitud_id)
    if tipo == "recibidas":
        consulta = consulta.filter(models.Postulacion.iniciada_por != usuario.rol)
    elif tipo == "enviadas":
        consulta = consulta.filter(models.Postulacion.iniciada_por == usuario.rol)
    filas = consulta.order_by(models.Postulacion.id.desc()).all()
    return [postulacion_out(p, usuario) for p in filas]


@router.get("/{postulacion_id}", response_model=PostulacionOut)
def ver_postulacion(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    return postulacion_out(_visible(db, postulacion_id, usuario), usuario)


@router.post("/{postulacion_id}/responder", response_model=PostulacionOut)
def responder_postulacion(
    postulacion_id: int,
    datos: RespuestaIn,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    p = _visible(db, postulacion_id, usuario)
    if p.iniciada_por == usuario.rol:
        raise HTTPException(status_code=403, detail="Solo la otra parte puede responder esta postulación")
    if p.estado != "Pendiente":
        raise HTTPException(status_code=409, detail=f"La postulación ya está {p.estado.lower()}")
    s = p.solicitud
    if not s.abierta:
        raise HTTPException(status_code=409, detail=f"La solicitud está {s.estado_api.lower()}")

    if datos.accion == "aceptar":
        p.estado = "Aceptada"
        p.fecha_respuesta = ahora()
        # Una solicitud se asigna a un solo estudiante: las demás pendientes se rechazan.
        for otra in s.postulaciones:
            if otra.id != p.id and otra.estado == "Pendiente":
                otra.estado = "Rechazada"
                otra.fecha_respuesta = ahora()
    else:
        p.estado = "Rechazada"
        p.fecha_respuesta = ahora()
    recalcular_estado_solicitud(s)
    db.commit()
    return postulacion_out(_visible(db, p.id, usuario), usuario)


@router.post("/{postulacion_id}/cancelar", response_model=PostulacionOut)
def cancelar_postulacion(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    p = _visible(db, postulacion_id, usuario)
    if p.estado == "Pendiente":
        if p.iniciada_por != usuario.rol:
            raise HTTPException(
                status_code=403,
                detail="Solo quien la inició puede cancelarla; si no te sirve, recházala",
            )
    elif p.estado != "Aceptada":
        raise HTTPException(status_code=409, detail=f"La postulación ya está {p.estado.lower()}")

    p.estado = "Cancelada"
    p.fecha_respuesta = ahora()
    for c in p.citas:
        if c.estado == "Agendada":
            c.estado = "Cancelada"
    recalcular_estado_solicitud(p.solicitud)
    db.commit()
    return postulacion_out(_visible(db, p.id, usuario), usuario)


@router.post("/{postulacion_id}/completar", response_model=PostulacionOut)
def completar_tratamiento(
    postulacion_id: int,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    """El estudiante declara que el tratamiento se realizó: suma al requerimiento."""
    p = _visible(db, postulacion_id, usuario)
    if p.estado != "Aceptada":
        raise HTTPException(status_code=409, detail="Solo se puede completar una postulación aceptada")
    if p.solicitud.estado_api == "Completada":
        raise HTTPException(status_code=409, detail="El tratamiento ya está completado")

    # La tabla del equipo queda en 'Asignado'; la fecha de término vive en solicitud_detalle.
    asegurar_detalle(p.solicitud).completada_en = ahora()
    for c in p.citas:
        if c.estado == "Agendada":
            c.estado = "Realizada"
    r = p.requerimiento
    if r is not None and r.estado == "Abierto":
        r.cantidad_completada = min(r.cantidad_completada + 1, r.cantidad_requerida)
        marcar_completado_si_corresponde(r)
    db.commit()
    return postulacion_out(_visible(db, p.id, usuario), usuario)
