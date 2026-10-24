"""
Funciones de seguridad:
- Hash y verificación de contraseñas (passlib + bcrypt)
- Creación y validación de tokens JWT (python-jose)
"""
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.vigencia import vencer_caducadas

load_dotenv()

# --- Config del token (cámbialas por variables de entorno reales en producción) ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("No se encontró SECRET_KEY en el archivo .env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 horas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar la sesión",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    usuario = db.query(models.Usuario).filter(models.Usuario.id == int(usuario_id)).first()
    if usuario is None:
        raise credentials_exception
    # Vence a los estudiantes cuyo certificado semestral caducó (ver app/vigencia.py).
    if vencer_caducadas(db):
        db.refresh(usuario)
    return usuario


def exigir_estudiante_verificado(usuario: models.Usuario) -> None:
    """
    Un estudiante solo puede interactuar con pacientes (postular, responder,
    agendar, publicar requerimientos) cuando su certificado fue verificado.
    Los pacientes no pasan por esta regla. Sin verificar puede seguir
    entrando y viendo los casos disponibles.
    """
    if usuario.rol != "estudiante":
        return
    perfil = usuario.perfil_estudiante
    if perfil is None or perfil.estado_verificacion != "Activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes verificar tu perfil de estudiante (certificado de alumno regular) para realizar esta acción",
        )


def require_estudiante_verificado(usuario: models.Usuario = Depends(get_current_user)) -> models.Usuario:
    """Dependencia: solo estudiantes con estado 'Activo'."""
    if usuario.rol != "estudiante":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para realizar esta acción",
        )
    exigir_estudiante_verificado(usuario)
    return usuario


def require_rol(*roles: str):
    """
    Dependencia para proteger endpoints por rol.
    Uso: usuario = Depends(require_rol("estudiante"))
    """
    def verificar(usuario: models.Usuario = Depends(get_current_user)) -> models.Usuario:
        if usuario.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para realizar esta acción",
            )
        return usuario

    return verificar
