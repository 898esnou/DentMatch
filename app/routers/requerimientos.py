"""
Requerimientos clínicos del estudiante (cada uno con su tutor):
- POST   /api/requerimientos              declarar uno nuevo
- GET    /api/requerimientos              los míos (?estado=Abierto|Completado|Cancelado)
- GET    /api/requerimientos/{id}
- PATCH  /api/requerimientos/{id}         editar datos
- POST   /api/requerimientos/{id}/avance  sumar procedimientos realizados (manual)
- DELETE /api/requerimientos/{id}         cancelar (no se borra: queda 'Cancelado')
Solo estudiantes, y cada uno ve únicamente los suyos.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.catalogos import AREAS, ESTADOS_REQUERIMIENTO
from app.database import get_db
from app.schemas_dominio import AvanceIn, RequerimientoIn, RequerimientoOut, RequerimientoUpdate

router = APIRouter(prefix="/api/requerimientos", tags=["requerimientos"])


def requerimiento_out(r: models.Requerimiento, pendientes: int = 0) -> RequerimientoOut:
    return RequerimientoOut(
        id=r.id,
        tratamiento=r.tratamiento,
        area=r.area,
        area_nombre=AREAS.get(r.area, r.area),
        tutor=r.tutor,
        catedra=r.catedra,
        cantidad_requerida=r.cantidad_requerida,
        cantidad_completada=r.cantidad_completada,
        restantes=max(r.cantidad_requerida - r.cantidad_completada, 0),
        plazo=r.plazo,
        detalle=r.detalle,
        estado=r.estado,
        fecha_creacion=r.fecha_creacion,
        postulaciones_pendientes=pendientes,
    )


def _pendientes_por_requerimiento(db: Session, ids: List[int]) -> dict:
    if not ids:
        return {}
    filas = (
        db.query(models.Postulacion.requerimiento_id, func.count(models.Postulacion.id))
        .filter(
            models.Postulacion.requerimiento_id.in_(ids),
            models.Postulacion.estado == "Pendiente",
        )
        .group_by(models.Postulacion.requerimiento_id)
        .all()
    )
    return dict(filas)


def _propio(db: Session, requerimiento_id: int, usuario: models.Usuario) -> models.Requerimiento:
    r = db.get(models.Requerimiento, requerimiento_id)
    if r is None or r.estudiante_id != usuario.id:
        raise HTTPException(status_code=404, detail="Requerimiento no encontrado")
    return r


def marcar_completado_si_corresponde(r: models.Requerimiento) -> None:
    """Se usa también al completar un tratamiento desde las postulaciones."""
    if r.estado == "Abierto" and r.cantidad_completada >= r.cantidad_requerida:
        r.estado = "Completado"


@router.post("", response_model=RequerimientoOut, status_code=status.HTTP_201_CREATED)
def declarar_requerimiento(
    datos: RequerimientoIn,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    r = models.Requerimiento(estudiante_id=usuario.id, **datos.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return requerimiento_out(r)


@router.get("", response_model=List[RequerimientoOut])
def listar_requerimientos(
    estado: Optional[str] = Query(None),
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_REQUERIMIENTO:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = db.query(models.Requerimiento).filter(models.Requerimiento.estudiante_id == usuario.id)
    if estado:
        consulta = consulta.filter(models.Requerimiento.estado == estado)
    filas = consulta.order_by(models.Requerimiento.id.desc()).all()
    pendientes = _pendientes_por_requerimiento(db, [r.id for r in filas])
    return [requerimiento_out(r, pendientes.get(r.id, 0)) for r in filas]


@router.get("/{requerimiento_id}", response_model=RequerimientoOut)
def ver_requerimiento(
    requerimiento_id: int,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    r = _propio(db, requerimiento_id, usuario)
    return requerimiento_out(r, _pendientes_por_requerimiento(db, [r.id]).get(r.id, 0))


@router.patch("/{requerimiento_id}", response_model=RequerimientoOut)
def editar_requerimiento(
    requerimiento_id: int,
    datos: RequerimientoUpdate,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    r = _propio(db, requerimiento_id, usuario)
    if r.estado == "Cancelado":
        raise HTTPException(status_code=409, detail="El requerimiento está cancelado")
    cambios = datos.model_dump(exclude_unset=True)
    # Estos campos son obligatorios: no se pueden dejar en blanco.
    for campo in ("tratamiento", "tutor", "area", "cantidad_requerida"):
        if campo in cambios and cambios[campo] is None:
            raise HTTPException(status_code=422, detail=f"'{campo}' no puede quedar vacío")
    nueva_cantidad = cambios.get("cantidad_requerida", r.cantidad_requerida)
    if nueva_cantidad < r.cantidad_completada:
        raise HTTPException(
            status_code=422,
            detail="La cantidad requerida no puede ser menor a lo ya completado",
        )
    for campo, valor in cambios.items():
        setattr(r, campo, valor)
    # Si se subió la cantidad, un requerimiento 'Completado' vuelve a estar abierto.
    if r.estado == "Completado" and r.cantidad_completada < r.cantidad_requerida:
        r.estado = "Abierto"
    marcar_completado_si_corresponde(r)
    db.commit()
    db.refresh(r)
    return requerimiento_out(r, _pendientes_por_requerimiento(db, [r.id]).get(r.id, 0))


@router.post("/{requerimiento_id}/avance", response_model=RequerimientoOut)
def registrar_avance(
    requerimiento_id: int,
    datos: AvanceIn,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    r = _propio(db, requerimiento_id, usuario)
    if r.estado != "Abierto":
        raise HTTPException(status_code=409, detail=f"El requerimiento está {r.estado.lower()}")
    r.cantidad_completada = min(r.cantidad_completada + datos.cantidad, r.cantidad_requerida)
    marcar_completado_si_corresponde(r)
    db.commit()
    db.refresh(r)
    return requerimiento_out(r, _pendientes_por_requerimiento(db, [r.id]).get(r.id, 0))


@router.delete("/{requerimiento_id}", response_model=RequerimientoOut)
def cancelar_requerimiento(
    requerimiento_id: int,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    r = _propio(db, requerimiento_id, usuario)
    if r.estado == "Completado":
        raise HTTPException(status_code=409, detail="Un requerimiento completado no se puede cancelar")
    r.estado = "Cancelado"
    db.commit()
    db.refresh(r)
    return requerimiento_out(r)
