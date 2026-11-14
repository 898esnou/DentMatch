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


def test_el_admin_ve_datos_y_certificado_de_la_solicitud(client, estudiante_nuevo):
    """Para revisar una solicitud, la lista trae los datos del estudiante y el estado de su último certificado."""
    from tests.test_verificacion import PDF_VALIDO

    admin = _crear_admin(client)
    # Sin certificado todavía.
    fila = admin.get("/api/admin/estudiantes").json()[0]
    assert fila["certificado_documento"] is None and fila["certificado_revision"] is None
    assert fila["fecha_registro"] is not None and fila["universidad"] and fila["rut"]

    r = client.post(
        "/api/verificacion/certificado",
        headers=estudiante_nuevo.headers,
        files={"archivo": ("certificado.pdf", PDF_VALIDO, "application/pdf")},
    )
    assert r.status_code == 201

    fila = admin.get("/api/admin/estudiantes?estado=En Verificación").json()[0]
    assert fila["certificado_documento"] and fila["certificado_tipo"] == "application/pdf"
    assert fila["certificado_revision"] == "Pendiente" and fila["certificado_fecha"] is not None
    # El administrador puede abrir el archivo y decidir.
    assert admin.get(f"/api/admin/estudiantes/{estudiante_nuevo.id}/certificado").status_code == 200
    r = admin.patch(
        f"/api/admin/estudiantes/{estudiante_nuevo.id}/verificacion",
        json={"estado": "Rechazado", "motivo": "No corresponde a Odontología"},
    )
    assert r.json()["certificado_revision"] == "Rechazada" and r.json()["certificado_resuelto_por"] == "admin"
    assert r.json()["certificado_motivo"] == "No corresponde a Odontología"
