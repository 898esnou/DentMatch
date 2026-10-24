"""
Esquemas Pydantic: definen la forma de los datos que entran y salen de la API.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- LOGIN ----------
class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str


# ---------- REGISTRO ----------
class RegistroRequest(BaseModel):
    nombre_completo: str = Field(..., max_length=150)
    correo: EmailStr
    contrasena: str = Field(..., min_length=6)
    rol: str = Field(..., pattern="^(estudiante|paciente|admin)$")

    # Campos opcionales, solo se usan si rol == "estudiante"
    universidad: Optional[str] = None
    ano_carrera: Optional[int] = None
    comuna_atencion: Optional[str] = None
    disponibilidad: Optional[str] = None


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
