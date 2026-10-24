"""Verificación de estudiantes por el administrador."""
from app import models
from app.auth import hash_password
from app.database import SessionLocal
from tests.conftest import Sesion


def _crear_admin(client):
    db = SessionLocal()
    db.add(models.Usuario(nombre_completo="Admin Prueba", rut="1-9", correo="admin@test.cl",
                          contrasena_hash=hash_password("123456"), rol="admin"))
    db.commit()
    db.close()
    token = client.post("/api/login", json={"correo": "admin@test.cl", "contrasena": "123456"}).json()["access_token"]
    return Sesion(client, 0, {"Authorization": f"Bearer {token}"}, "Admin")


def test_admin_verifica_estudiantes(client, estudiante_nuevo, paciente):
    admin = _crear_admin(client)
    lista = admin.get("/api/admin/estudiantes?estado=No verificado").json()
    assert [e["id"] for e in lista] == [estudiante_nuevo.id]  # los pacientes no aparecen
    assert paciente.get("/api/estudiantes").json() == []       # sin verificar, no es visible

    r = admin.patch(f"/api/admin/estudiantes/{estudiante_nuevo.id}/verificacion", json={"estado": "Activo"})
    assert r.status_code == 200 and r.json()["estado_verificacion"] == "Activo"
    assert paciente.get("/api/estudiantes").json()[0]["id"] == estudiante_nuevo.id
    estudiante = estudiante_nuevo
    assert admin.patch(f"/api/admin/estudiantes/{estudiante.id}/verificacion", json={"estado": "Otro"}).status_code == 422
    assert admin.patch(f"/api/admin/estudiantes/{paciente.id}/verificacion", json={"estado": "Activo"}).status_code == 404
