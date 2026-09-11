"""
Configuración de la conexión a PostgreSQL usando SQLAlchemy.
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

# Pequeña validación por si a algún compañero se le olvida crear su .env
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("No se encontró DATABASE_URL en el archivo .env")

# Resto de la configuración original
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()