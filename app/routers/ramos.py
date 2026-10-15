"""
Ramos / clínicas del estudiante ("Mis Clínicas por Ramo"):
- GET    /api/ramos
- POST   /api/ramos
- PUT    /api/ramos/{id}
- DELETE /api/ramos/{id}
Solo estudiantes, y cada uno ve y edita únicamente los suyos.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.database import get_db
from app.schemas_dominio import RamoIn, RamoOut

router = APIRouter(prefix="/api/ramos", tags=["ramos"])


def _validar_horario(datos: RamoIn) -> None:
    if datos.hora_inicio and datos.hora_fin and datos.hora_fin <= datos.hora_inicio:
        raise HTTPException(status_code=422, detail="La hora de término debe ser posterior a la de inicio")


def _ramo_propio(db: Session, ramo_id: int, usuario: models.Usuario) -> models.RamoEstudiante:
    ramo = db.get(models.RamoEstudiante, ramo_id)
    if ramo is None or ramo.estudiante_id != usuario.id:
        raise HTTPException(status_code=404, detail="Ramo no encontrado")
    return ramo


@router.get("", response_model=List[RamoOut])
def listar_ramos(
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.RamoEstudiante)
        .filter(models.RamoEstudiante.estudiante_id == usuario.id)
        .order_by(models.RamoEstudiante.id)
        .all()
    )


@router.post("", response_model=RamoOut, status_code=status.HTTP_201_CREATED)
def crear_ramo(
    datos: RamoIn,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    _validar_horario(datos)
    ramo = models.RamoEstudiante(estudiante_id=usuario.id, **datos.model_dump())
    db.add(ramo)
    db.commit()
    db.refresh(ramo)
    return ramo


@router.put("/{ramo_id}", response_model=RamoOut)
def actualizar_ramo(
    ramo_id: int,
    datos: RamoIn,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    _validar_horario(datos)
    ramo = _ramo_propio(db, ramo_id, usuario)
    for campo, valor in datos.model_dump().items():
        setattr(ramo, campo, valor)
    db.commit()
    db.refresh(ramo)
    return ramo


@router.delete("/{ramo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_ramo(
    ramo_id: int,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    db.delete(_ramo_propio(db, ramo_id, usuario))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
