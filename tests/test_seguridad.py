"""Roles, sesión y datos privados."""
from tests.conftest import REQUERIMIENTO, SOLICITUD


def test_endpoints_exigen_sesion(client):
    for ruta in ("/api/requerimientos", "/api/solicitudes", "/api/casos", "/api/postulaciones",
                 "/api/citas", "/api/resumen", "/api/ramos", "/api/estudiantes"):
        assert client.get(ruta).status_code == 401, ruta


def test_cada_rol_solo_accede_a_lo_suyo(estudiante, paciente):
    assert paciente.get("/api/requerimientos").status_code == 403
    assert paciente.get("/api/casos").status_code == 403
    assert paciente.get("/api/ramos").status_code == 403
    assert estudiante.get("/api/solicitudes").status_code == 403
    assert estudiante.get("/api/estudiantes").status_code == 403
    assert estudiante.post("/api/solicitudes", json=SOLICITUD).status_code == 403
    assert paciente.post("/api/requerimientos", json=REQUERIMIENTO).status_code == 403


def test_registro_publico_no_crea_admin(client):
    r = client.post("/api/registro", data={
        "nombre_completo": "Intruso Admin", "rut": "9.999.999-9", "correo": "x@test.cl",
        "contrasena": "123456", "rol": "admin",
    })
    assert r.status_code == 400


def test_admin_no_accesible_a_otros_roles(estudiante, paciente):
    assert estudiante.get("/api/admin/estudiantes").status_code == 403
    assert paciente.get("/api/admin/estudiantes").status_code == 403


def test_nunca_se_expone_rut_ni_correo(estudiante, paciente):
    caso = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    casos = estudiante.get("/api/casos").text
    assert "pac@test.cl" not in casos and "33.333.333-3" not in casos
    assert "Camila Soto M." in casos  # solo el nombre abreviado
    lista = paciente.get("/api/estudiantes").text
    assert "est@test.cl" not in lista and "11.111.111-1" not in lista
    assert "Matías Rojas V." in lista
    assert caso["codigo"].startswith("SOL-")
