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

if SQLALCHEMY_DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
    # Tests (SQLite en memoria): una única conexión compartida, porque cada conexión nueva
    # sería una base vacía. Sirve solo para peticiones de a una, como las de pytest.
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
elif SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Servidor de prueba de Postman (archivo SQLite temporal): una conexión por petición, así
    # aguanta peticiones en paralelo (el chat pide la lista y el hilo a la vez).
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping: el pooler de Supabase cierra las conexiones inactivas; así la app las comprueba
    # antes de usarlas y no falla la primera petición tras un rato sin tráfico (típico en Vercel).
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
