"""
Esquemas Pydantic del dominio de DentMatch: ramos, requerimientos, solicitudes,
postulaciones, citas, resumen y administración.
(Los de login/registro/perfil siguen en schemas.py.)
"""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.catalogos import AREAS, DIAS_SEMANA, ESTADOS_VERIFICACION

Area = Literal[tuple(AREAS)]
DiaSemana = Literal[tuple(DIAS_SEMANA)]
Verificacion = Literal[tuple(ESTADOS_VERIFICACION)]
HORA = r"^([01]\d|2[0-3]):[0-5]\d$"  # "08:30"


# ---------- RAMOS (clínicas del estudiante) ----------
class RamoIn(BaseModel):
    ramo: str = Field(..., min_length=2, max_length=100)
    area: Area = "otra"
    tutor: Optional[str] = Field(None, max_length=150)
    dia_semana: Optional[DiaSemana] = None
    hora_inicio: Optional[str] = Field(None, pattern=HORA)
    hora_fin: Optional[str] = Field(None, pattern=HORA)
    clinica: Optional[str] = Field(None, max_length=150)
    lugar: Optional[str] = Field(None, max_length=200)


class RamoOut(RamoIn):
    id: int

    class Config:
        from_attributes = True


# ---------- REQUERIMIENTOS ----------
class RequerimientoIn(BaseModel):
    tratamiento: str = Field(..., min_length=2, max_length=150)
    area: Area = "otra"
    tutor: str = Field(..., min_length=2, max_length=150)
    catedra: Optional[str] = Field(None, max_length=150)
    cantidad_requerida: int = Field(1, ge=1, le=50)
    plazo: Optional[date] = None
    detalle: Optional[str] = None


class RequerimientoUpdate(BaseModel):
    tratamiento: Optional[str] = Field(None, min_length=2, max_length=150)
    area: Optional[Area] = None
    tutor: Optional[str] = Field(None, min_length=2, max_length=150)
    catedra: Optional[str] = Field(None, max_length=150)
    cantidad_requerida: Optional[int] = Field(None, ge=1, le=50)
    plazo: Optional[date] = None
    detalle: Optional[str] = None


class AvanceIn(BaseModel):
    cantidad: int = Field(1, ge=1, le=50)


class RequerimientoOut(BaseModel):
    id: int
    tratamiento: str
    area: str
    area_nombre: str
    tutor: str
    catedra: Optional[str] = None
    cantidad_requerida: int
    cantidad_completada: int
    restantes: int
    plazo: Optional[date] = None
    detalle: Optional[str] = None
    estado: str
    fecha_creacion: Optional[datetime] = None
    postulaciones_pendientes: int = 0


# ---------- SOLICITUDES (paciente) ----------
class SolicitudIn(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=200)
    descripcion: str = Field(..., min_length=10)
    area: Area = "diagnostico"
    urgente: bool = False
    comuna: Optional[str] = Field(None, max_length=100)
    distancia_max_km: Optional[int] = Field(None, ge=1, le=100)
    disponibilidad: Optional[str] = None
    preferencia: Optional[str] = Field(None, max_length=150)


class SolicitudUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=200)
    descripcion: Optional[str] = Field(None, min_length=10)
    area: Optional[Area] = None
    urgente: Optional[bool] = None
    comuna: Optional[str] = Field(None, max_length=100)
    distancia_max_km: Optional[int] = Field(None, ge=1, le=100)
    disponibilidad: Optional[str] = None
    preferencia: Optional[str] = Field(None, max_length=150)


class SolicitudOut(BaseModel):
    id: int
    codigo: str
    titulo: str
    descripcion: str
    area: str
    area_nombre: str
    urgente: bool
    comuna: Optional[str] = None
    distancia_max_km: Optional[int] = None
    disponibilidad: Optional[str] = None
    preferencia: Optional[str] = None
    estado: str
    fecha_creacion: Optional[datetime] = None
    total_postulaciones: int = 0
    postulaciones_pendientes: int = 0


# ---------- CASOS (lo que ve el estudiante) ----------
class CasoOut(BaseModel):
    id: int
    codigo: str
    titulo: str
    descripcion: str
    area: str
    area_nombre: str
    urgente: bool
    comuna: Optional[str] = None
    disponibilidad: Optional[str] = None
    paciente: str  # nombre abreviado
    estado: str
    fecha_creacion: Optional[datetime] = None
    mi_postulacion_id: Optional[int] = None
    mi_postulacion_estado: Optional[str] = None


# ---------- ESTUDIANTES (lo que ve el paciente) ----------
class RequerimientoResumen(BaseModel):
    id: int
    tratamiento: str
    area: str
    tutor: str
    restantes: int


class EstudianteOut(BaseModel):
    id: int
    nombre: str  # abreviado
    universidad: str
    ano_carrera: int
    comuna_atencion: str
    disponibilidad: Optional[str] = None
    estado_verificacion: Optional[str] = None
    areas: List[str] = []
    tutores: List[str] = []
    ramos: List[str] = []
    requerimientos_abiertos: List[RequerimientoResumen] = []
    mi_postulacion_estado: Optional[str] = None


# ---------- POSTULACIONES ----------
class PostulacionIn(BaseModel):
    solicitud_id: int
    # Lo envía el paciente (a quién solicita). Si postula un estudiante, se ignora.
    estudiante_id: Optional[int] = None
    requerimiento_id: Optional[int] = None
    mensaje: Optional[str] = Field(None, max_length=1000)


class RespuestaIn(BaseModel):
    accion: Literal["aceptar", "rechazar"]


class SolicitudResumen(BaseModel):
    id: int
    codigo: str
    titulo: str
    area: str
    estado: str
    comuna: Optional[str] = None


class ParticipanteOut(BaseModel):
    id: int
    nombre: str  # abreviado


class PostulacionOut(BaseModel):
    id: int
    solicitud: SolicitudResumen
    estudiante: ParticipanteOut
    paciente: ParticipanteOut
    requerimiento: Optional[RequerimientoResumen] = None
    iniciada_por: str
    estado: str
    mensaje: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_respuesta: Optional[datetime] = None
    puede_responder: bool = False


# ---------- CITAS ----------
class CitaIn(BaseModel):
    postulacion_id: int
    fecha_hora: datetime
    lugar: Optional[str] = Field(None, max_length=200)
    notas: Optional[str] = None


class CitaUpdate(BaseModel):
    fecha_hora: Optional[datetime] = None
    lugar: Optional[str] = Field(None, max_length=200)
    notas: Optional[str] = None
    estado: Optional[Literal["Realizada", "Cancelada"]] = None


class CitaOut(BaseModel):
    id: int
    postulacion_id: int
    fecha_hora: datetime
    lugar: Optional[str] = None
    notas: Optional[str] = None
    estado: str
    solicitud_codigo: str
    titulo: str
    estudiante: ParticipanteOut
    paciente: ParticipanteOut


# ---------- RESUMEN (cabecera de cada portal) ----------
class ResumenOut(BaseModel):
    rol: str
    # estudiante
    requerimientos_abiertos: Optional[int] = None
    requerimientos_completados: Optional[int] = None
    postulaciones_recibidas: Optional[int] = None  # de pacientes, esperando mi respuesta
    ramos: Optional[List[str]] = None
    # paciente
    solicitudes_activas: Optional[int] = None
    tratamientos_completados: Optional[int] = None
    # ambos
    postulaciones_pendientes: int = 0  # esperando respuesta de la otra parte
    citas_proximas: int = 0
    notificaciones: int = 0  # cosas que requieren mi acción


# ---------- ADMIN ----------
class EstudianteAdminOut(BaseModel):
    id: int
    nombre_completo: str
    correo: str
    rut: Optional[str] = None
    universidad: str
    ano_carrera: int
    estado_verificacion: Optional[str] = None
    certificado_documento: Optional[str] = None


class VerificacionIn(BaseModel):
    estado: Verificacion
