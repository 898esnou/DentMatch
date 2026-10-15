"""
Los tests corren contra SQLite en memoria: NUNCA tocan Supabase.

Se hace ANTES de importar la app:
- DATABASE_URL apunta a SQLite y load_dotenv se anula (database.py usa
  override=True, así que sin esto el .env real pisaría la variable).
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "clave-solo-para-tests"

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
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


def crear_sesion(client, rol, correo, rut, nombre, **extra):
    datos = {"nombre_completo": nombre, "rut": rut, "correo": correo, "contrasena": "123456", "rol": rol}
    if rol == "estudiante":
        datos.update({"universidad": "Universidad de Chile", "ano_carrera": 5})
    datos.update(extra)
    r = client.post("/api/registro", data=datos)
    assert r.status_code == 201, r.text
    login = client.post("/api/login", json={"correo": correo, "contrasena": "123456"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return Sesion(client, r.json()["id"], {"Authorization": f"Bearer {token}"}, nombre)


@pytest.fixture()
def estudiante(client):
    return crear_sesion(client, "estudiante", "est@test.cl", "11.111.111-1", "Matías Rojas Valenzuela")


@pytest.fixture()
def estudiante2(client):
    return crear_sesion(client, "estudiante", "est2@test.cl", "22.222.222-2", "Sofía Navarrete Castro")


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
