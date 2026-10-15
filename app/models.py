"""
Modelos SQLAlchemy que reflejan las tablas de Supabase.

Tablas del equipo (no se modifican): usuarios, perfil_estudiante, solicitudes,
catalogo_tratamientos.
Tablas de este backend: perfil_paciente, ramos_estudiante, requerimientos,
solicitud_detalle, postulaciones, citas. Se crean solas al arrancar (create_all);
create_all nunca altera una tabla que ya existe.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, ForeignKey, Integer, String, Text,
    TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.catalogos import ESTADOS_CITA, ESTADOS_POSTULACION, ESTADOS_REQUERIMIENTO, sql_in
from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre_completo = Column(String(150), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    contrasena_hash = Column(String(255), nullable=False)  # nunca texto plano
    rol = Column(String(20), nullable=False)  # 'estudiante' | 'paciente' | 'admin'
    fecha_registro = Column(TIMESTAMP, server_default=func.now())
    rut = Column(String(20), unique=True, index=True)

    __table_args__ = (
        CheckConstraint("rol IN ('estudiante', 'paciente', 'admin')", name="chk_rol"),
    )

    perfil_estudiante = relationship(
        "PerfilEstudiante",
        back_populates="usuario",
        uselist=False,
        cascade="all, delete-orphan",
    )
    perfil_paciente = relationship(
        "PerfilPaciente",
        back_populates="usuario",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PerfilEstudiante(Base):
    __tablename__ = "perfil_estudiante"

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    universidad = Column(String(150), nullable=False)
    ano_carrera = Column(Integer, nullable=False)
    comuna_atencion = Column(String(100), nullable=False)
    disponibilidad = Column(Text)
    estado_verificacion = Column(String(30), default="En Verificación")
    # NOTA: certificado_documento queda como columna opcional (nullable) en la
    # base de datos. El formulario de este prototipo TODAVÍA no lo pide
    # (se agregará en una etapa posterior), así que puede quedar en NULL.
    certificado_documento = Column(String(255))

    __table_args__ = (
        CheckConstraint(
            "estado_verificacion IN ('En Verificación', 'Activo', 'Rechazado')",
            name="chk_estado_verificacion",
        ),
    )

    usuario = relationship("Usuario", back_populates="perfil_estudiante")


class PerfilPaciente(Base):
    __tablename__ = "perfil_paciente"

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    comuna = Column(String(100))
    tratamiento_requerido = Column(String(150))
    descripcion = Column(Text)
    disponibilidad = Column(Text)

    usuario = relationship("Usuario", back_populates="perfil_paciente")


class RamoEstudiante(Base):
    """Un ramo/clínica del estudiante, con su tutor y su horario semanal."""
    __tablename__ = "ramos_estudiante"

    id = Column(Integer, primary_key=True, index=True)
    estudiante_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ramo = Column(String(100), nullable=False)
    area = Column(String(30), nullable=False, default="otra")
    tutor = Column(String(150))
    dia_semana = Column(String(15))
    hora_inicio = Column(String(5))  # "08:30"
    hora_fin = Column(String(5))     # "12:30"
    clinica = Column(String(150))
    lugar = Column(String(200))


class Requerimiento(Base):
    """Procedimiento clínico obligatorio que el estudiante declara (con su tutor)."""
    __tablename__ = "requerimientos"

    id = Column(Integer, primary_key=True, index=True)
    estudiante_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tratamiento = Column(String(150), nullable=False)
    area = Column(String(30), nullable=False, default="otra")
    tutor = Column(String(150), nullable=False)
    catedra = Column(String(150))
    cantidad_requerida = Column(Integer, nullable=False, default=1)
    cantidad_completada = Column(Integer, nullable=False, default=0)
    plazo = Column(Date)
    detalle = Column(Text)
    estado = Column(String(20), nullable=False, default="Abierto")
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"estado IN ({sql_in(ESTADOS_REQUERIMIENTO)})", name="chk_estado_requerimiento"),
        CheckConstraint("cantidad_requerida >= 1", name="chk_cantidad_requerida"),
        CheckConstraint("cantidad_completada >= 0", name="chk_cantidad_completada"),
    )

    estudiante = relationship("Usuario")


class CatalogoTratamiento(Base):
    """
    Tabla del EQUIPO (no se modifica). Es el catálogo al que la IA clasifica
    cada solicitud (solicitudes.tratamiento_clasificado_id).
    """
    __tablename__ = "catalogo_tratamientos"

    id = Column(Integer, primary_key=True)
    nombre_oficial = Column(String(150), nullable=False)
    descripcion_tecnica = Column(Text)


class Solicitud(Base):
    """
    Necesidad de atención dental que publica un paciente.

    La tabla `solicitudes` es del EQUIPO (ya existía en Supabase y no se altera):
    sus columnas se usan tal cual, y la IA completa `tratamiento_clasificado_id`.
    Lo que esa tabla no tiene (título, área, urgencia, disponibilidad…) vive en
    `solicitud_detalle`. El estado de la tabla del equipo solo admite
    Buscando / Asignado / Cancelado; los estados que ve la API (Abierta,
    En Revisión, Asignada, Completada, Cancelada) se derivan en `estado_api`.
    """
    __tablename__ = "solicitudes"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    descripcion = Column("descripcion_coloquial", Text, nullable=False)
    tratamiento_clasificado_id = Column(Integer, ForeignKey("catalogo_tratamientos.id"))
    comuna = Column("comuna_paciente", String(100), nullable=False)
    estado = Column(String(20), default="Buscando")  # Buscando | Asignado | Cancelado
    fecha_creacion = Column("fecha_solicitud", TIMESTAMP, server_default=func.now())

    # Mismo CHECK que la tabla real, para que los tests lo detecten si se rompe.
    __table_args__ = (
        CheckConstraint("estado IN ('Buscando', 'Asignado', 'Cancelado')", name="solicitudes_estado_check"),
    )

    paciente = relationship("Usuario")
    tratamiento_clasificado = relationship("CatalogoTratamiento")
    detalle = relationship(
        "SolicitudDetalle", back_populates="solicitud", uselist=False,
        cascade="all, delete-orphan", lazy="joined",
    )
    postulaciones = relationship(
        "Postulacion", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def codigo(self) -> str:
        return f"SOL-{self.id:04d}"

    @property
    def abierta(self) -> bool:
        """Se puede postular / solicitar mientras el equipo la tenga en 'Buscando'."""
        return self.estado == "Buscando"

    # --- campos de solicitud_detalle (con valores por defecto si la fila la creó otra app) ---
    @property
    def titulo(self) -> str:
        if self.detalle and self.detalle.titulo:
            return self.detalle.titulo
        texto = self.descripcion or ""
        return texto if len(texto) <= 60 else texto[:57] + "…"

    @property
    def area(self) -> str:
        return self.detalle.area if self.detalle else "diagnostico"

    @property
    def urgente(self) -> bool:
        return bool(self.detalle and self.detalle.urgente)

    @property
    def distancia_max_km(self):
        return self.detalle.distancia_max_km if self.detalle else None

    @property
    def disponibilidad(self):
        return self.detalle.disponibilidad if self.detalle else None

    @property
    def preferencia(self):
        return self.detalle.preferencia if self.detalle else None

    @property
    def estado_api(self) -> str:
        """Abierta | En Revisión | Asignada | Completada | Cancelada (ver ESTADOS_SOLICITUD)."""
        if self.estado == "Cancelado":
            return "Cancelada"
        if self.estado == "Asignado":
            return "Completada" if self.detalle and self.detalle.completada_en else "Asignada"
        pendientes = any(p.estado == "Pendiente" for p in self.postulaciones)
        return "En Revisión" if pendientes else "Abierta"


class SolicitudDetalle(Base):
    """Datos extra de una solicitud que la tabla del equipo no tiene (1 a 1)."""
    __tablename__ = "solicitud_detalle"

    solicitud_id = Column(
        Integer, ForeignKey("solicitudes.id", ondelete="CASCADE"), primary_key=True
    )
    titulo = Column(String(200))
    area = Column(String(30), nullable=False, default="diagnostico")
    urgente = Column(Boolean, nullable=False, default=False)
    distancia_max_km = Column(Integer)
    disponibilidad = Column(Text)
    preferencia = Column(String(150))  # ej: "Clínica U. de Chile preferente"
    completada_en = Column(TIMESTAMP)  # cuándo el estudiante marcó el tratamiento como realizado

    solicitud = relationship("Solicitud", back_populates="detalle")


class Postulacion(Base):
    """
    Vínculo entre una solicitud (paciente) y un estudiante. Lo inicia cualquiera
    de los dos (iniciada_por) y lo responde la contraparte.
    """
    __tablename__ = "postulaciones"

    id = Column(Integer, primary_key=True, index=True)
    solicitud_id = Column(
        Integer, ForeignKey("solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estudiante_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requerimiento_id = Column(Integer, ForeignKey("requerimientos.id", ondelete="SET NULL"))
    iniciada_por = Column(String(20), nullable=False)  # 'estudiante' | 'paciente'
    estado = Column(String(20), nullable=False, default="Pendiente")
    mensaje = Column(Text)
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())
    fecha_respuesta = Column(TIMESTAMP)

    __table_args__ = (
        UniqueConstraint("solicitud_id", "estudiante_id", name="uq_postulacion_solicitud_estudiante"),
        CheckConstraint(f"estado IN ({sql_in(ESTADOS_POSTULACION)})", name="chk_estado_postulacion"),
        CheckConstraint("iniciada_por IN ('estudiante', 'paciente')", name="chk_iniciada_por"),
    )

    solicitud = relationship("Solicitud", back_populates="postulaciones")
    estudiante = relationship("Usuario")
    requerimiento = relationship("Requerimiento")
    citas = relationship("Cita", back_populates="postulacion", cascade="all, delete-orphan")


class Cita(Base):
    """Sesión agendada para una postulación aceptada."""
    __tablename__ = "citas"

    id = Column(Integer, primary_key=True, index=True)
    postulacion_id = Column(
        Integer, ForeignKey("postulaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha_hora = Column(TIMESTAMP, nullable=False)
    lugar = Column(String(200))
    notas = Column(Text)
    estado = Column(String(20), nullable=False, default="Agendada")
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"estado IN ({sql_in(ESTADOS_CITA)})", name="chk_estado_cita"),
    )

    postulacion = relationship("Postulacion", back_populates="citas")
