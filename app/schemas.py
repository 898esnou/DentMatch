"""
Esquemas Pydantic: definen la forma de los datos que entran y salen de la API.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ---------- LOGIN ----------
class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str


# ---------- REGISTRO (solo para poder crear usuarios de prueba) ----------
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

    class Config:
        from_attributes = True
