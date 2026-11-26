"""
Administración (solo rol admin):
- GET   /api/admin/estudiantes                    (?estado=No verificado|En Verificación|Activo|Rechazado)
- PATCH /api/admin/estudiantes/{id}/verificacion  {estado, motivo?}  (motivo: qué debe corregir si se rechaza)
- GET   /api/admin/estudiantes/{id}/certificado   descarga el último certificado (bucket privado)
El rol admin no se puede crear desde el registro público: usa scripts/crear_admin.py
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, contains_eager

from app import almacenamiento, models
from app.auth import require_rol
from app.catalogos import ESTADOS_VERIFICACION
from app.database import get_db
from app.schemas_dominio import EstudianteAdminOut, VerificacionIn
from app.servicios import ahora

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _out(u: models.Usuario, ultima: Optional[models.VerificacionEstudiante] = None) -> EstudianteAdminOut:
    """Datos del estudiante + su último certificado, para revisar la verificación con todo a la vista."""
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
        fecha_registro=u.fecha_registro,
        certificado_fecha=ultima.fecha_subida if ultima else None,
        certificado_tipo=ultima.tipo_contenido if ultima else None,
        certificado_revision=ultima.estado if ultima else None,
        certificado_resuelto_por=ultima.resuelta_por if ultima else None,
        certificado_motivo=ultima.motivo if ultima else None,
    )


def _ultimas_verificaciones(db: Session, ids: List[int]) -> dict:
    """Último certificado subido por cada estudiante (una sola consulta)."""
    if not ids:
        return {}
    V = models.VerificacionEstudiante
    ultimas: dict = {}
    for v in db.query(V).filter(V.estudiante_id.in_(ids)).order_by(V.id).all():
        ultimas[v.estudiante_id] = v   # el último por id queda al final
    return ultimas


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
        .options(contains_eager(models.Usuario.perfil_estudiante))  # el perfil viene en la misma consulta
        .filter(models.Usuario.rol == "estudiante")
    )
    if estado:
        consulta = consulta.filter(models.PerfilEstudiante.estado_verificacion == estado)
    usuarios = consulta.order_by(models.Usuario.id).all()
    ultimas = _ultimas_verificaciones(db, [u.id for u in usuarios])
    return [_out(u, ultimas.get(u.id)) for u in usuarios]


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
    if datos.estado == "Rechazado" and not (datos.motivo or "").strip():
        raise HTTPException(status_code=422, detail="Indica el motivo del rechazo para que el estudiante sepa qué corregir")
    u.perfil_estudiante.estado_verificacion = datos.estado

    # El último certificado subido queda resuelto con esta decisión.
    V = models.VerificacionEstudiante
    ultima = db.query(V).filter(V.estudiante_id == u.id).order_by(V.id.desc()).first()
    if ultima is not None and datos.estado in ("Activo", "Rechazado"):
        ultima.estado = "Aprobada" if datos.estado == "Activo" else "Rechazada"
        rechazada = datos.estado == "Rechazado"
        ultima.motivo = (datos.motivo or "").strip() if rechazada else None
        ultima.resuelta_por = "admin"
        ultima.fecha_resolucion = ahora()
    db.commit()
    db.refresh(u)
    return _out(u, ultima)


@router.get("/estudiantes/{estudiante_id}/certificado")
def descargar_certificado(
    estudiante_id: int,
    _: models.Usuario = Depends(require_rol("admin")),
    db: Session = Depends(get_db),
):
    """Entrega el último certificado del estudiante. Solo admin: el bucket es privado."""
    V = models.VerificacionEstudiante
    ultima = db.query(V).filter(V.estudiante_id == estudiante_id).order_by(V.id.desc()).first()
    if ultima is None:
        raise HTTPException(status_code=404, detail="Este estudiante no ha subido un certificado")
    try:
        contenido = almacenamiento.leer(ultima.archivo)
    except almacenamiento.ErrorAlmacenamiento:
        raise HTTPException(status_code=404, detail="No se encontró el archivo del certificado")
    return Response(
        content=contenido,
        media_type=ultima.tipo_contenido,
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )
