"""
Configuración de la conexión a PostgreSQL (Supabase) usando SQLAlchemy.
Lee la URL de conexión desde el archivo .env (nunca la escribas directo aquí).
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Carga las variables del archivo .env al entorno de Python
load_dotenv(override=True)

# Obtiene la URL de la base de datos de forma segura
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Pequeña validación por si se te olvida crear tu .env
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("No se encontró DATABASE_URL en el archivo .env")

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Solo para los tests (SQLite en memoria): una única conexión compartida.
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
