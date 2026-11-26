"""
Rutas de autenticación:
- POST /api/registro -> crea un usuario (estudiante o paciente). El documento
                        (RUT chileno o extranjero) debe ser válido; el paciente queda
                        habilitado de inmediato, el estudiante debe verificar su certificado.
- POST /api/login    -> valida correo + contraseña y devuelve un token JWT
- GET  /api/me       -> datos del usuario autenticado

El correo no distingue mayúsculas: "Ana@Mail.cl" y "ana@mail.cl" son la misma cuenta.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import LARGO_MAXIMO_CONTRASENA, create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.documentos import TIPOS_DOCUMENTO, normalizar_documento, variantes_guardadas
from app.sanciones import verificar_cuenta

router = APIRouter(prefix="/api", tags=["auth"])

ANO_MINIMO_ESTUDIANTE = 4          # solo estudiantes de 4° año o superior atienden pacientes
_VALIDADOR_CORREO = TypeAdapter(EmailStr)


def _normalizar_correo(correo: str) -> str:
    """Valida el formato y lo deja en minúsculas y sin espacios (forma en que se guarda)."""
    limpio = (correo or "").strip().lower()
    try:
        _VALIDADOR_CORREO.validate_python(limpio)
    except ValidationError:
        raise HTTPException(status_code=400, detail="El correo no tiene un formato válido")
    return limpio


def buscar_por_correo(db: Session, correo: str) -> Optional[models.Usuario]:
    """Busca sin distinguir mayúsculas (hay cuentas antiguas guardadas con mayúsculas)."""
    return db.query(models.Usuario).filter(func.lower(models.Usuario.correo) == correo.strip().lower()).first()


@router.post("/registro", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    nombre_completo: str = Form(..., min_length=3, max_length=150),
    rut: str = Form(..., max_length=30),
    tipo_documento: str = Form("rut"),  # "rut" (chileno) | "extranjero" (pasaporte u otro)
    correo: str = Form(..., max_length=150),
    contrasena: str = Form(..., min_length=6, max_length=LARGO_MAXIMO_CONTRASENA),
    rol: str = Form(...),
    universidad: Optional[str] = Form(None, max_length=150),
    ano_carrera: Optional[int] = Form(None, ge=1, le=10),
    db: Session = Depends(get_db),
):
    # El rol admin NO se puede crear desde el registro público (ver scripts/crear_admin.py).
    if rol not in ("estudiante", "paciente"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    if tipo_documento not in TIPOS_DOCUMENTO:
        raise HTTPException(status_code=400, detail="Tipo de documento inválido")

    nombre_completo = " ".join(nombre_completo.split())
    correo = _normalizar_correo(correo)
    if buscar_por_correo(db, correo):
        raise HTTPException(status_code=400, detail="Ese correo ya está registrado")

    # Documento de identidad: se valida y se guarda siempre en su forma canónica
    # ('12.345.678-5'), para que el mismo RUT no se pueda registrar escrito distinto.
    try:
        rut = normalizar_documento(tipo_documento, rut)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if db.query(models.Usuario).filter(models.Usuario.rut.in_(variantes_guardadas(rut))).first():
        raise HTTPException(status_code=400, detail="Este documento ya está registrado en el sistema")

    # Validar siempre en el backend: el frontend se puede saltar.
    if rol == "estudiante" and (ano_carrera is None or ano_carrera < ANO_MINIMO_ESTUDIANTE):
        raise HTTPException(
            status_code=400,
            detail="Los estudiantes deben estar cursando 4to año o superior",
        )

    nuevo_usuario = models.Usuario(
        nombre_completo=nombre_completo,
        rut=rut,
        correo=correo,
        contrasena_hash=hash_password(contrasena),
        rol=rol,
    )
    db.add(nuevo_usuario)
    db.flush()  # asigna el id sin confirmar: usuario y perfil se guardan juntos o no se guarda nada

    if rol == "estudiante":
        # El estudiante entra "No verificado" y verifica su perfil desde el portal
        # subiendo su certificado de alumno regular (app/routers/verificacion.py).
        db.add(models.PerfilEstudiante(
            usuario_id=nuevo_usuario.id,
            universidad=(universidad or "").strip() or "Por definir",
            ano_carrera=ano_carrera,
            comuna_atencion="Por definir",
            estado_verificacion="No verificado",
        ))
    else:
        db.add(models.PerfilPaciente(usuario_id=nuevo_usuario.id))
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario


@router.post("/login", response_model=schemas.TokenResponse)
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = buscar_por_correo(db, datos.correo)

    # Mensaje genérico a propósito: no revelar si falló el correo o la contraseña.
    if not usuario or not verify_password(datos.contrasena, usuario.contrasena_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )
    verificar_cuenta(db, usuario)  # si está baneado o en time-out, se le explica

    token = create_access_token(data={"sub": str(usuario.id), "rol": usuario.rol})
    return schemas.TokenResponse(
        access_token=token,
        rol=usuario.rol,
        nombre_completo=usuario.nombre_completo,
    )


@router.get("/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario_actual: models.Usuario = Depends(get_current_user)):
    return usuario_actual
