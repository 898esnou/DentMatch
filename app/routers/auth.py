"""
Rutas de autenticación:
- POST /api/registro -> crea un usuario (estudiante o paciente). El documento
                        (RUT chileno o extranjero) debe ser válido; el paciente queda
                        habilitado de inmediato, el estudiante debe verificar su certificado.
- POST /api/login    -> valida correo + contraseña y devuelve un token JWT
- GET  /api/me       -> datos del usuario autenticado
"""
from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.documentos import normalizar_documento, variantes_guardadas

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/registro", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    nombre_completo: str = Form(...),
    rut: str = Form(...),
    tipo_documento: str = Form("rut"),  # "rut" (chileno) | "extranjero" (pasaporte u otro)
    correo: str = Form(...),
    contrasena: str = Form(...),
    rol: str = Form(...),
    universidad: str = Form(None),
    ano_carrera: int = Form(None),
    db: Session = Depends(get_db),
):
    # El rol admin NO se puede crear desde el registro público.
    if rol not in ("estudiante", "paciente"):
        raise HTTPException(status_code=400, detail="Rol inválido")

    if db.query(models.Usuario).filter(models.Usuario.correo == correo).first():
        raise HTTPException(status_code=400, detail="Ese correo ya está registrado")

    # Documento de identidad: se valida y se guarda siempre en su forma canónica
    # ('12345678-5'), para que el mismo RUT no se pueda registrar escrito distinto.
    try:
        rut = normalizar_documento(tipo_documento, rut)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    if db.query(models.Usuario).filter(models.Usuario.rut.in_(variantes_guardadas(rut))).first():
        raise HTTPException(status_code=400, detail="Este documento ya está registrado en el sistema")

    # Validar siempre en el backend: el frontend se puede saltar.
    if rol == "estudiante" and (ano_carrera is None or ano_carrera < 4):
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
    db.commit()
    db.refresh(nuevo_usuario)

    if rol == "estudiante":
        # El estudiante entra "No verificado" y verifica su perfil desde el portal
        # subiendo su certificado de alumno regular (app/routers/verificacion.py).
        db.add(models.PerfilEstudiante(
            usuario_id=nuevo_usuario.id,
            universidad=universidad or "Por definir",
            ano_carrera=ano_carrera,
            comuna_atencion="Por definir",
            disponibilidad=None,
            certificado_documento=None,
            estado_verificacion="No verificado",
        ))
    else:
        db.add(models.PerfilPaciente(usuario_id=nuevo_usuario.id))
    db.commit()

    return nuevo_usuario


@router.post("/login", response_model=schemas.TokenResponse)
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == datos.correo).first()

    # Mensaje genérico a propósito: no revelar si falló el correo o la contraseña.
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Correo o contraseña incorrectos",
    )
    if not usuario or not verify_password(datos.contrasena, usuario.contrasena_hash):
        raise credenciales_invalidas

    token = create_access_token(data={"sub": str(usuario.id), "rol": usuario.rol})
    return schemas.TokenResponse(
        access_token=token,
        rol=usuario.rol,
        nombre_completo=usuario.nombre_completo,
    )


@router.get("/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario_actual: models.Usuario = Depends(get_current_user)):
    return usuario_actual
