"""
Modelos SQLAlchemy que reflejan EXACTAMENTE las tablas 1 y 2 de tu script SQL:
- usuarios
- perfil_estudiante

Si ya creaste las tablas manualmente en PostgreSQL (con tu script SQL), no necesitas
correr Base.metadata.create_all() de nuevo: SQLAlchemy solo se conecta a lo que ya existe.
"""
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, TIMESTAMP, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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

    # Relación 1 a 1 con el perfil de estudiante (solo existe si rol = 'estudiante')
    perfil_estudiante = relationship(
        "PerfilEstudiante",
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
    disponibilidad = Column(Text)  # texto libre o JSON serializado como string
    estado_verificacion = Column(String(30), default="En Verificación")
    certificado_documento = Column(String(255))  # ruta del archivo subido (PDF/imagen)

    __table_args__ = (
        CheckConstraint(
            "estado_verificacion IN ('En Verificación', 'Activo', 'Rechazado')",
            name="chk_estado_verificacion",
        ),
    )

    usuario = relationship("Usuario", back_populates="perfil_estudiante")
