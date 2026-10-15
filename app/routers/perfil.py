"""
Rutas de perfil (cada rol edita solo el suyo):
- GET /api/perfil              -> usuario + perfil según su rol
- PUT /api/perfil/estudiante   -> actualiza perfil de estudiante
- PUT /api/perfil/paciente     -> actualiza perfil de paciente
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, require_rol
from app.database import get_db

router = APIRouter(prefix="/api/perfil", tags=["perfil"])


@router.get("", response_model=schemas.PerfilOut)
def obtener_perfil(usuario: models.Usuario = Depends(get_current_user)):
    return schemas.PerfilOut(
        usuario=usuario,
        estudiante=usuario.perfil_estudiante,
        paciente=usuario.perfil_paciente,
    )


@router.put("/estudiante", response_model=schemas.PerfilEstudianteOut)
def actualizar_perfil_estudiante(
    datos: schemas.PerfilEstudianteUpdate,
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    perfil = usuario.perfil_estudiante
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(perfil, campo, valor)
    db.commit()
    db.refresh(perfil)
    return perfil


@router.put("/paciente", response_model=schemas.PerfilPacienteOut)
def actualizar_perfil_paciente(
    datos: schemas.PerfilPacienteUpdate,
    usuario: models.Usuario = Depends(require_rol("paciente")),
    db: Session = Depends(get_db),
):
    perfil = usuario.perfil_paciente
    if perfil is None:  # cuentas creadas antes de existir esta tabla
        perfil = models.PerfilPaciente(usuario_id=usuario.id)
        db.add(perfil)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(perfil, campo, valor)
    db.commit()
    db.refresh(perfil)
    return perfil
