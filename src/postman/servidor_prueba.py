"""
Servidor de PRUEBA para Postman: usa una base SQLite temporal y NUNCA toca Supabase.

Crea un administrador de prueba (admin@prueba.cl / prueba123) y deja la API escuchando.
Los certificados y la IA no se usan (la moderación corre solo con reglas locales).

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python -m postman.servidor_prueba            # puerto 8011
    python -m postman.servidor_prueba 8020       # otro puerto
"""
import os
import sys
import tempfile

# Todo esto debe ir ANTES de importar la app (igual que tests/conftest.py).
BD = os.path.join(tempfile.mkdtemp(prefix="dentmatch-postman-"), "prueba.db")
os.environ["DATABASE_URL"] = "sqlite:///" + BD.replace("\\", "/")
os.environ["SECRET_KEY"] = "clave-solo-para-pruebas-con-postman"
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="dentmatch-postman-archivos-")
os.environ["MODERACION_IA"] = "0"
for var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_MODERACION"):
    os.environ.pop(var, None)

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False  # que no se lea el .env real

import uvicorn  # noqa: E402

from app import models  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402

assert str(engine.url).startswith("sqlite"), "El servidor de prueba no puede usar la base real"

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(models.Usuario(nombre_completo="Admin Prueba", rut="1.111.111-1", correo="admin@prueba.cl",
                          contrasena_hash=hash_password("prueba123"), rol="admin"))
    db.commit()
    db.close()
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
    print(f"Servidor de prueba en http://127.0.0.1:{puerto}  (administrador: admin@prueba.cl / prueba123)")
    uvicorn.run("app.main:app", host="127.0.0.1", port=puerto, log_level="warning")
