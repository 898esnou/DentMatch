"""
Esquemas Pydantic de autenticación y perfil: la forma de los datos que entran y salen de la API.
(El registro llega como formulario multipart, así que sus campos se validan en app/routers/auth.py.)
Los esquemas del resto del dominio están en schemas_dominio.py.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- LOGIN ----------
class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str = Field(..., max_length=72)  # límite de bcrypt (ver app/auth.py)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str


# ---------- USUARIO ----------
class UsuarioOut(BaseModel):
    id: int
    nombre_completo: str
    correo: EmailStr
    rol: str

    model_config = ConfigDict(from_attributes=True)


# ---------- PERFILES ----------
class PerfilEstudianteOut(BaseModel):
    universidad: str
    ano_carrera: int
    comuna_atencion: str
    disponibilidad: Optional[str] = None
    estado_verificacion: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PerfilEstudianteUpdate(BaseModel):
    universidad: Optional[str] = Field(None, max_length=150)
    comuna_atencion: Optional[str] = Field(None, max_length=100)
    disponibilidad: Optional[str] = None


class PerfilPacienteOut(BaseModel):
    comuna: Optional[str] = None
    tratamiento_requerido: Optional[str] = None
    descripcion: Optional[str] = None
    disponibilidad: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PerfilPacienteUpdate(BaseModel):
    comuna: Optional[str] = Field(None, max_length=100)
    tratamiento_requerido: Optional[str] = Field(None, max_length=150)
    descripcion: Optional[str] = None
    disponibilidad: Optional[str] = None


class PerfilOut(BaseModel):
    """Usuario + el perfil que corresponde a su rol (uno de los dos queda en None)."""
    usuario: UsuarioOut
    estudiante: Optional[PerfilEstudianteOut] = None
    paciente: Optional[PerfilPacienteOut] = None
