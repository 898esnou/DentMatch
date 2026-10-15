"""
Administración (solo rol admin):
- GET   /api/admin/estudiantes                    (?estado=En Verificación|Activo|Rechazado)
- PATCH /api/admin/estudiantes/{id}/verificacion  {estado}
El rol admin no se puede crear desde el registro público: usa scripts/crear_admin.py
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.catalogos import ESTADOS_VERIFICACION
from app.database import get_db
from app.schemas_dominio import EstudianteAdminOut, VerificacionIn

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _out(u: models.Usuario) -> EstudianteAdminOut:
    p = u.perfil_estudiante
    return EstudianteAdminOut(
        id=u.id,
        nombre_completo=u.nombre_completo,
        correo=u.correo,
        rut=u.rut,
        universidad=p.universidad,
        ano_carrera=p.ano_carrera,
        estado_verificacion=p.estado_verificacion,
        certificado_documento=p.certificado_documento,
    )


@router.get("/estudiantes", response_model=List[EstudianteAdminOut])
def listar_estudiantes(
    estado: Optional[str] = Query(None),
    _: models.Usuario = Depends(require_rol("admin")),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_VERIFICACION:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = (
        db.query(models.Usuario)
        .join(models.PerfilEstudiante, models.PerfilEstudiante.usuario_id == models.Usuario.id)
        .filter(models.Usuario.rol == "estudiante")
    )
    if estado:
        consulta = consulta.filter(models.PerfilEstudiante.estado_verificacion == estado)
    return [_out(u) for u in consulta.order_by(models.Usuario.id).all()]


@router.patch("/estudiantes/{estudiante_id}/verificacion", response_model=EstudianteAdminOut)
def cambiar_verificacion(
    estudiante_id: int,
    datos: VerificacionIn,
    _: models.Usuario = Depends(require_rol("admin")),
    db: Session = Depends(get_db),
):
    u = db.get(models.Usuario, estudiante_id)
    if u is None or u.rol != "estudiante" or u.perfil_estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    u.perfil_estudiante.estado_verificacion = datos.estado
    db.commit()
    db.refresh(u)
    return _out(u)
