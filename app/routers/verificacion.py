"""
Verificación del perfil del estudiante (certificado de alumno regular):
- GET  /api/verificacion              mi estado, el motivo si fue rechazado y si puedo subir
- POST /api/verificacion/certificado  subir (o renovar) el certificado: PDF, JPG o PNG, hasta 5 MB

Flujo:
  No verificado --sube--> En Verificación --(sistema o admin)--> Activo | Rechazado
  Rechazado --vuelve a subir--> En Verificación
  Activo --renueva--> sigue Activo mientras se revisa el nuevo certificado

La verificación automática por QR aún no existe (ver app/verificacion_certificado.py):
por ahora todo certificado queda "En Verificación" para revisión manual del admin.
"""
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import almacenamiento, models
from app.auth import require_rol
from app.database import get_db
from app.schemas_dominio import VerificacionEstadoOut
from app import vigencia
from app.servicios import ahora
from app.verificacion_certificado import verificar_automaticamente

router = APIRouter(prefix="/api/verificacion", tags=["verificacion"])

TAMANO_MAXIMO = 5 * 1024 * 1024        # 5 MB
SUBIDAS_MAXIMAS_POR_DIA = 5            # evita llenar el almacenamiento

# Tipo de archivo según sus primeros bytes ("firma"). No confiamos en el nombre
# ni en el Content-Type que declara el navegador: se pueden falsificar.
FIRMAS = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)

MENSAJES = {
    "No verificado": "Sube tu certificado de alumno regular para verificar tu perfil.",
    "En Verificación": "Recibimos tu certificado y lo estamos revisando.",
    "Activo": "Tu perfil está verificado.",
    "Rechazado": "No pudimos verificar tu certificado. Revisa el motivo y vuelve a subirlo.",
}


def _detectar_tipo(contenido: bytes):
    for firma, tipo_contenido, extension in FIRMAS:
        if contenido.startswith(firma):
            return tipo_contenido, extension
    return None


def _ultima(db: Session, estudiante_id: int) -> Optional[models.VerificacionEstudiante]:
    V = models.VerificacionEstudiante
    return db.query(V).filter(V.estudiante_id == estudiante_id).order_by(V.id.desc()).first()


def estado_out(db: Session, usuario: models.Usuario) -> VerificacionEstadoOut:
    perfil = usuario.perfil_estudiante
    ultima = _ultima(db, usuario.id)
    estado = perfil.estado_verificacion or "No verificado"
    # El motivo solo tiene sentido mientras el estado sea Rechazado.
    motivo = ultima.motivo if (ultima and estado == "Rechazado") else None
    vig = vigencia.vigencia_de(db, usuario.id) if estado == "Activo" else None
    hoy = ahora().date()
    en_gracia = bool(vig and vig.en_gracia(hoy))
    mensaje = MENSAJES.get(estado, "")
    if en_gracia:
        mensaje = (
            f"Tu certificado del semestre terminó. Sube uno nuevo antes del {vig.gracia_hasta:%d-%m-%Y} "
            "para no perder el acceso."
        )
    return VerificacionEstadoOut(
        estado=estado,
        mensaje=mensaje,
        vence_el=vig.vence_el if vig else None,
        en_gracia=en_gracia,
        acceso_hasta=vig.gracia_hasta if vig else None,
        motivo=motivo,
        certificado_subido=ultima is not None,
        fecha_subida=ultima.fecha_subida if ultima else None,
        puede_subir=estado != "En Verificación",  # mientras se revisa no se acumulan envíos
    )


@router.get("", response_model=VerificacionEstadoOut)
def ver_estado(
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    return estado_out(db, usuario)


@router.post("/certificado", response_model=VerificacionEstadoOut, status_code=status.HTTP_201_CREATED)
def subir_certificado(
    archivo: UploadFile = File(...),
    usuario: models.Usuario = Depends(require_rol("estudiante")),
    db: Session = Depends(get_db),
):
    perfil = usuario.perfil_estudiante
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil de estudiante no encontrado")
    if perfil.estado_verificacion == "En Verificación":
        raise HTTPException(status_code=409, detail="Tu certificado anterior todavía se está revisando")

    V = models.VerificacionEstudiante
    ayer = ahora() - timedelta(days=1)
    recientes = db.query(V).filter(V.estudiante_id == usuario.id, V.fecha_subida >= ayer).count()
    if recientes >= SUBIDAS_MAXIMAS_POR_DIA:
        raise HTTPException(status_code=429, detail="Subiste demasiados certificados hoy. Inténtalo mañana")

    # Se lee un byte de más para detectar archivos demasiado grandes sin cargarlos enteros.
    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 5 MB")
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    tipo = _detectar_tipo(contenido)
    if tipo is None:
        raise HTTPException(status_code=422, detail="Formato no permitido: sube un PDF, JPG o PNG")
    tipo_contenido, extension = tipo

    ruta = f"estudiante_{usuario.id}/{uuid.uuid4().hex}.{extension}"
    try:
        almacenamiento.guardar(ruta, contenido, tipo_contenido)
    except almacenamiento.ErrorAlmacenamiento:
        raise HTTPException(status_code=503, detail="No pudimos guardar tu certificado. Inténtalo de nuevo en un momento")

    registro = V(
        estudiante_id=usuario.id,
        archivo=ruta,
        tipo_contenido=tipo_contenido,
        tamano_bytes=len(contenido),
        estado="Pendiente",
    )
    db.add(registro)
    perfil.certificado_documento = ruta

    # Un estudiante ya verificado que renueva no pierde el acceso mientras se revisa.
    estaba_activo = perfil.estado_verificacion == "Activo"
    if not estaba_activo:
        perfil.estado_verificacion = "En Verificación"

    resultado = verificar_automaticamente(contenido, tipo_contenido, usuario.nombre_completo, usuario.rut)
    if resultado is not None:
        registro.fecha_resolucion = ahora()
        registro.resuelta_por = "sistema"
        registro.fecha_emision = resultado.fecha_emision
        if resultado.aprobada:
            registro.estado = "Aprobada"
            perfil.estado_verificacion = "Activo"
        else:
            registro.estado = "Rechazada"
            registro.motivo = resultado.motivo
            perfil.estado_verificacion = "Rechazado"

    db.commit()
    db.refresh(usuario)
    return estado_out(db, usuario)
