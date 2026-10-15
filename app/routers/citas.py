"""
Citas de una postulación aceptada:
- POST  /api/citas          agendar (solo el estudiante)
- GET   /api/citas          las mías (?estado=, ?proximas=true)
- PATCH /api/citas/{id}     el estudiante cambia fecha/lugar/notas o marca Realizada/Cancelada;
                            el paciente solo puede cancelar
"""
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app import models
from app.auth import require_rol
from app.catalogos import ESTADOS_CITA
from app.database import get_db
from app.schemas_dominio import CitaIn, CitaOut, CitaUpdate, ParticipanteOut
from app.servicios import ahora
from app.utils import nombre_corto

router = APIRouter(prefix="/api/citas", tags=["citas"])

ambos_roles = require_rol("estudiante", "paciente")


def _sin_zona(fecha):
    """Los TIMESTAMP se guardan sin zona horaria: si llega con zona, la quitamos."""
    return fecha.replace(tzinfo=None) if fecha.tzinfo else fecha


def _validar_futuro(fecha) -> None:
    if _sin_zona(fecha) < ahora() - timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="La fecha de la cita no puede estar en el pasado")


def cita_out(c: models.Cita) -> CitaOut:
    p = c.postulacion
    s = p.solicitud
    return CitaOut(
        id=c.id,
        postulacion_id=p.id,
        fecha_hora=c.fecha_hora,
        lugar=c.lugar,
        notas=c.notas,
        estado=c.estado,
        solicitud_codigo=s.codigo,
        titulo=s.titulo,
        estudiante=ParticipanteOut(id=p.estudiante_id, nombre=nombre_corto(p.estudiante.nombre_completo)),
        paciente=ParticipanteOut(id=s.paciente_id, nombre=nombre_corto(s.paciente.nombre_completo)),
    )


def _base(db: Session):
    return (
        db.query(models.Cita)
        .join(models.Postulacion, models.Cita.postulacion_id == models.Postulacion.id)
        .join(models.Solicitud, models.Postulacion.solicitud_id == models.Solicitud.id)
        .options(
            joinedload(models.Cita.postulacion).joinedload(models.Postulacion.estudiante),
            joinedload(models.Cita.postulacion).joinedload(models.Postulacion.solicitud)
            .joinedload(models.Solicitud.paciente),
        )
    )


def _filtrar_por_usuario(consulta, usuario: models.Usuario):
    if usuario.rol == "estudiante":
        return consulta.filter(models.Postulacion.estudiante_id == usuario.id)
    return consulta.filter(models.Solicitud.paciente_id == usuario.id)


@router.post("", response_model=CitaOut, status_code=status.HTTP_201_CREATED)
def agendar_cita(
    datos: CitaIn,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    p = db.get(models.Postulacion, datos.postulacion_id)
    if p is None or p.estudiante_id != usuario.id:
        raise HTTPException(status_code=404, detail="Postulación no encontrada")
    if p.estado != "Aceptada":
        raise HTTPException(status_code=409, detail="Solo se puede agendar una postulación aceptada")
    if p.solicitud.estado_api != "Asignada":
        raise HTTPException(status_code=409, detail=f"La solicitud está {p.solicitud.estado_api.lower()}")
    _validar_futuro(datos.fecha_hora)

    c = models.Cita(
        postulacion_id=p.id,
        fecha_hora=_sin_zona(datos.fecha_hora),
        lugar=datos.lugar,
        notas=datos.notas,
    )
    db.add(c)
    db.commit()
    return cita_out(_base(db).filter(models.Cita.id == c.id).one())


@router.get("", response_model=List[CitaOut])
def listar_citas(
    estado: Optional[str] = Query(None),
    proximas: bool = Query(False, description="Solo las agendadas desde ahora en adelante"),
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_CITA:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = _filtrar_por_usuario(_base(db), usuario)
    if estado:
        consulta = consulta.filter(models.Cita.estado == estado)
    if proximas:
        consulta = consulta.filter(models.Cita.estado == "Agendada", models.Cita.fecha_hora >= ahora())
    return [cita_out(c) for c in consulta.order_by(models.Cita.fecha_hora).all()]


@router.patch("/{cita_id}", response_model=CitaOut)
def actualizar_cita(
    cita_id: int,
    datos: CitaUpdate,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    c = _filtrar_por_usuario(_base(db), usuario).filter(models.Cita.id == cita_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if c.estado != "Agendada":
        raise HTTPException(status_code=409, detail=f"La cita ya está {c.estado.lower()}")

    cambios = datos.model_dump(exclude_unset=True)
    if usuario.rol == "paciente":
        if set(cambios) - {"estado"} or cambios.get("estado") != "Cancelada":
            raise HTTPException(status_code=403, detail="Un paciente solo puede cancelar la cita")
    if cambios.get("fecha_hora") is None:
        cambios.pop("fecha_hora", None)
    else:
        _validar_futuro(cambios["fecha_hora"])
        cambios["fecha_hora"] = _sin_zona(cambios["fecha_hora"])
    if cambios.get("estado") is None:
        cambios.pop("estado", None)
    for campo, valor in cambios.items():
        setattr(c, campo, valor)
    db.commit()
    return cita_out(_base(db).filter(models.Cita.id == cita_id).one())
