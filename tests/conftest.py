"""
Los tests corren contra SQLite en memoria: NUNCA tocan Supabase.

Se hace ANTES de importar la app:
- DATABASE_URL apunta a SQLite y load_dotenv se anula (database.py usa
  override=True, así que sin esto el .env real pisaría la variable).
"""
import os

import tempfile

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "clave-solo-para-tests"
# Los certificados de los tests van a una carpeta temporal y nunca a Supabase Storage.
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="dentmatch-tests-")
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

assert str(engine.url).startswith("sqlite"), "¡Los tests no pueden usar la base real!"


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


class Sesion:
    """Un usuario ya registrado y con sesión iniciada."""

    def __init__(self, client, id_, headers, nombre):
        self.client, self.id, self.headers, self.nombre = client, id_, headers, nombre

    def get(self, ruta, **kw):
        return self.client.get(ruta, headers=self.headers, **kw)

    def post(self, ruta, json=None, **kw):
        return self.client.post(ruta, headers=self.headers, json=json, **kw)

    def patch(self, ruta, json=None, **kw):
        return self.client.patch(ruta, headers=self.headers, json=json, **kw)

    def put(self, ruta, json=None, **kw):
        return self.client.put(ruta, headers=self.headers, json=json, **kw)

    def delete(self, ruta, **kw):
        return self.client.delete(ruta, headers=self.headers, **kw)


def marcar_estado_verificacion(usuario_id, estado):
    """Cambia directo en la base el estado de verificación de un estudiante (atajo de tests)."""
    db = SessionLocal()
    try:
        db.get(models.PerfilEstudiante, usuario_id).estado_verificacion = estado
        db.commit()
    finally:
        db.close()


def crear_sesion(client, rol, correo, rut, nombre, verificado=True, **extra):
    """
    Registra y inicia sesión. Los estudiantes quedan ya verificados ('Activo') para que
    los tests del flujo normal no tengan que repetir la verificación; usa verificado=False
    para probar al estudiante nuevo.
    """
    datos = {"nombre_completo": nombre, "rut": rut, "correo": correo, "contrasena": "123456", "rol": rol}
    if rol == "estudiante":
        datos.update({"universidad": "Universidad de Chile", "ano_carrera": 5})
    datos.update(extra)
    r = client.post("/api/registro", data=datos)
    assert r.status_code == 201, r.text
    login = client.post("/api/login", json={"correo": correo, "contrasena": "123456"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    if rol == "estudiante" and verificado:
        marcar_estado_verificacion(r.json()["id"], "Activo")
    return Sesion(client, r.json()["id"], {"Authorization": f"Bearer {token}"}, nombre)


@pytest.fixture()
def estudiante(client):
    return crear_sesion(client, "estudiante", "est@test.cl", "11.111.111-1", "Matías Rojas Valenzuela")


@pytest.fixture()
def estudiante2(client):
    return crear_sesion(client, "estudiante", "est2@test.cl", "22.222.222-2", "Sofía Navarrete Castro")


@pytest.fixture()
def estudiante_nuevo(client):
    """Estudiante recién registrado: todavía 'No verificado'."""
    return crear_sesion(client, "estudiante", "nuevo@test.cl", "15.555.555-6", "Daniela Ortiz Peña", verificado=False)


@pytest.fixture()
def paciente(client):
    return crear_sesion(client, "paciente", "pac@test.cl", "33.333.333-3", "Camila Soto Morales")


@pytest.fixture()
def paciente2(client):
    return crear_sesion(client, "paciente", "pac2@test.cl", "44.444.444-4", "Jorge Pérez Díaz")


SOLICITUD = {
    "titulo": "Dolor en molar inferior",
    "descripcion": "Me duele al masticar en una muela de abajo desde hace una semana",
    "area": "endodoncia",
    "urgente": True,
    "comuna": "Providencia",
    "disponibilidad": "Martes por la tarde",
}

REQUERIMIENTO = {
    "tratamiento": "Endodoncia unirradicular",
    "area": "endodoncia",
    "tutor": "Prof. Ricardo",
    "cantidad_requerida": 2,
    "plazo": "2026-12-15",
}

# Archivos mínimos que cumplen la "firma" de cada formato (basta para las validaciones).
PDF_VALIDO = b"%PDF-1.4\n%certificado de prueba\n"
PNG_VALIDO = b"\x89PNG\r\n\x1a\n" + b"0" * 32
