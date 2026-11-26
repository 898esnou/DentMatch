"""
Esquemas Pydantic del dominio de DentMatch: ramos, requerimientos, solicitudes,
postulaciones, chat, resumen y administración.
(Los de login/registro/perfil siguen en schemas.py.)
"""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

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

    model_config = ConfigDict(from_attributes=True)


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
    descripcion: str = Field(..., min_length=10, max_length=500)
    area: Area = "diagnostico"
    urgente: bool = False
    comuna: Optional[str] = Field(None, max_length=100)
    distancia_max_km: Optional[int] = Field(None, ge=1, le=100)
    disponibilidad: Optional[str] = None
    preferencia: Optional[str] = Field(None, max_length=150)


class SolicitudUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=200)
    descripcion: Optional[str] = Field(None, min_length=10, max_length=500)
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
    # Pendiente y la inició el paciente: el estudiante decide (aceptar o rechazar).
    mi_postulacion_puede_responder: bool = False


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
    # Coincidencia con la solicitud del paciente (0 a 100, ver app/matching.py).
    # Solo viene cuando se pide con ?solicitud_id= o en los resultados de la búsqueda.
    puntaje: Optional[int] = None
    motivos: List[str] = []


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
    notificaciones: int = 0  # cosas que requieren mi acción
    estado_verificacion: Optional[str] = None  # solo estudiante


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
    # Para revisar la solicitud con todo a la vista (datos + último certificado).
    fecha_registro: Optional[datetime] = None
    certificado_fecha: Optional[datetime] = None
    certificado_tipo: Optional[str] = None
    certificado_revision: Optional[str] = None   # 'Pendiente' | 'Aprobada' | 'Rechazada'
    certificado_resuelto_por: Optional[str] = None  # 'sistema' | 'admin'
    certificado_motivo: Optional[str] = None


class VerificacionIn(BaseModel):
    estado: Verificacion
    # Se muestra al estudiante cuando el estado es "Rechazado" (qué debe corregir).
    motivo: Optional[str] = Field(None, max_length=500)


class VerificacionEstadoOut(BaseModel):
    """Estado de verificación del estudiante, para su portal."""
    estado: str
    mensaje: str
    motivo: Optional[str] = None
    certificado_subido: bool = False
    fecha_subida: Optional[datetime] = None
    puede_subir: bool = True
    vence_el: Optional[date] = None        # fin del semestre del certificado (solo Activo)
    en_gracia: bool = False                # el semestre terminó y corre el plazo para renovar
    acceso_hasta: Optional[date] = None    # último día con acceso mientras está en gracia


# ---------- CHAT ----------
class MensajeIn(BaseModel):
    contenido: str = Field(..., min_length=1, max_length=1000)


class MensajeOut(BaseModel):
    id: int
    mio: bool                      # lo escribí yo (se dibuja a la derecha)
    contenido: str
    fecha_creacion: datetime
    leido: bool                    # la otra persona ya lo vio


class ConversacionOut(BaseModel):
    postulacion_id: int
    solicitud_codigo: str
    titulo: str
    otra_parte: ParticipanteOut
    puede_escribir: bool           # solo con la postulación Aceptada y el tratamiento en curso
    no_leidos: int
    ultimo_mensaje: Optional[str] = None
    ultima_fecha: Optional[datetime] = None
    se_borra_el: Optional[datetime] = None  # solo si la conversación está cerrada
    cerrada_por_moderacion: bool = False
    mensaje_cierre: Optional[str] = None    # explicación para quien no fue sancionado
    archivada: bool = False                 # una de las dos personas la archivó (solo lectura, se puede reabrir)
    archivada_por_mi: bool = False          # la archivé yo: solo yo puedo reabrirla
    bloqueada: bool = False                 # una de las dos personas bloqueó al otro (solo lectura)
    bloqueada_por_mi: bool = False          # bloqueé yo: solo yo puedo desbloquear


class MensajeInapropiadoOut(BaseModel):
    """Mensaje que la moderación bloqueó y no llegó: se muestra solo si quien lo lee decide verlo."""
    id: int
    contenido: str
    categoria: str
    fecha: datetime


class HiloOut(BaseModel):
    conversacion: ConversacionOut
    mensajes: List[MensajeOut]
    # Lo que escribió la otra persona y se bloqueó; solo cuando su cuenta fue sancionada (chat detenido).
    mensajes_inapropiados: List[MensajeInapropiadoOut] = []
    puede_reportar: bool = False                 # ya hay suficientes mensajes y no reporté aún
    aviso_moderacion: Optional[str] = None       # recordatorio de "Reportar" tras un mensaje bloqueado


class ReporteIn(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=500)


class ReporteCreadoOut(BaseModel):
    id: int
    mensaje: str


# ---------- AVISOS ----------
class AvisoOut(BaseModel):
    id: int
    texto: str
    fecha: datetime


# ---------- ADMIN: MODERACIÓN ----------
DecisionReporte = Literal["baneo", "suspension", "descartar"]


class DecisionIn(BaseModel):
    decision: DecisionReporte
    dias: Optional[int] = Field(None, ge=1, le=90)        # solo para "suspension"
    mensaje: Optional[str] = Field(None, max_length=300)  # lo verá la persona sancionada
    nota: Optional[str] = Field(None, max_length=500)     # nota interna, solo la ven los admin


class PersonaAdminOut(BaseModel):
    id: int
    nombre: str
    rol: str
    estado_cuenta: str                       # activo | suspendido | baneado
    advertencias: int                        # advertencias vigentes (últimos 30 días)


class ReporteListaOut(BaseModel):
    id: int
    origen: str                              # usuario | automatico
    estado: str                              # Pendiente | Resuelto
    decision: Optional[str] = None
    motivo: str
    fecha_creacion: datetime
    reportado: PersonaAdminOut
    reportante: Optional[str] = None         # nombre de quien reportó (None si es automático)


class MensajeEvidenciaOut(BaseModel):
    de_reportado: bool
    autor: str
    contenido: str
    fecha: datetime


class BloqueadoEvidenciaOut(BaseModel):
    contenido: str
    categoria: str
    fuente: str                              # reglas | ia
    fecha: datetime


class ResolucionOut(BaseModel):
    decision: str
    nota: Optional[str] = None
    dias: Optional[int] = None
    resuelto_por: Optional[str] = None
    fecha: Optional[datetime] = None


class ReporteDetalleOut(ReporteListaOut):
    otra_persona: Optional[str] = None       # la contraparte en la conversación
    conversacion: Optional[str] = None       # título de la solicitud
    reportes_previos: int = 0                # otros reportes contra la misma persona
    mensajes: List[MensajeEvidenciaOut] = []
    bloqueados: List[BloqueadoEvidenciaOut] = []
    resolucion: Optional[ResolucionOut] = None


class CuentaAdminOut(BaseModel):
    id: int
    nombre_completo: str
    correo: str
    rol: str
    estado_cuenta: str
    suspendido_hasta: Optional[datetime] = None
    motivo: Optional[str] = None
    advertencias: int
    reportes_recibidos: int


class ResumenAdminOut(BaseModel):
    reportes_pendientes: int
    reportes_automaticos_pendientes: int
    reportes_resueltos_30d: int
    cuentas_baneadas: int
    cuentas_suspendidas: int
    verificaciones_pendientes: int
