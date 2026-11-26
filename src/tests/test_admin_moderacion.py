"""Panel de administración: reportes, decisiones, cuentas y resumen (Épica 5)."""
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.servicios import ahora
from tests.test_admin import _crear_admin
from tests.test_chat import _enviar, _vinculo


def _banear_por_insultos(estudiante, pid):
    for texto in ("idiota", "imbécil", "te voy a matar"):
        _enviar(estudiante, pid, texto)


def _reportar(sesion, pid, otro=None, motivo="La otra persona se comportó mal"):
    """Deja 3 mensajes en la conversación (alternando con `otro` si se indica) y reporta."""
    for i, texto in enumerate(("Hola", "Hola, ¿cómo estás?", "Bien, ¿el martes te sirve?")):
        _enviar(otro if (otro and i % 2) else sesion, pid, texto)
    r = sesion.post(f"/api/chat/{pid}/reportar", json={"motivo": motivo})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _login(client, correo, contrasena="123456"):
    return client.post("/api/login", json={"correo": correo, "contrasena": contrasena})


# ---------------------------------------------------------------- permisos
def test_solo_el_admin_entra_a_la_moderacion(paciente, estudiante):
    rutas = [("get", "/api/admin/reportes"), ("get", "/api/admin/reportes/1"), ("get", "/api/admin/cuentas"),
             ("get", "/api/admin/resumen"), ("post", "/api/admin/cuentas/1/levantar-sancion"),
             ("post", "/api/admin/reportes/1/resolver")]
    for metodo, ruta in rutas:
        for sesion in (paciente, estudiante):
            r = getattr(sesion, metodo)(ruta, **({"json": {"decision": "descartar"}} if metodo == "post" else {}))
            assert r.status_code == 403, (metodo, ruta, r.status_code)


# ---------------------------------------------------------------- bandeja y detalle
def test_bandeja_pone_primero_los_automaticos_y_el_detalle_trae_la_evidencia(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    _reportar(paciente, pid, otro=estudiante)   # reporte de una persona contra el estudiante
    _banear_por_insultos(estudiante, pid)    # y luego el baneo automático

    lista = admin.get("/api/admin/reportes").json()
    assert [r["origen"] for r in lista] == ["automatico", "usuario"]
    auto = lista[0]
    assert auto["reportante"] is None and auto["reportado"]["estado_cuenta"] == "baneado"
    assert auto["reportado"]["nombre"] == "Matías Rojas Valenzuela"

    detalle = admin.get(f"/api/admin/reportes/{auto['id']}").json()
    assert detalle["otra_persona"] == "Camila Soto Morales" and detalle["conversacion"]
    assert [b["contenido"] for b in detalle["bloqueados"]] == ["idiota", "imbécil", "te voy a matar"]
    assert {b["fuente"] for b in detalle["bloqueados"]} == {"reglas"}
    assert [m["de_reportado"] for m in detalle["mensajes"]] == [False, True, False]
    assert detalle["reportes_previos"] == 1 and detalle["resolucion"] is None

    assert admin.get("/api/admin/reportes/9999").status_code == 404
    assert admin.get("/api/admin/reportes?estado=Otro").status_code == 422
    assert admin.get("/api/admin/reportes?estado=Resuelto").json() == []


def test_resumen(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    _banear_por_insultos(estudiante, pid)
    r = admin.get("/api/admin/resumen").json()
    assert r["reportes_pendientes"] == 1 and r["reportes_automaticos_pendientes"] == 1
    assert r["cuentas_baneadas"] == 1 and r["cuentas_suspendidas"] == 0 and r["reportes_resueltos_30d"] == 0


# ---------------------------------------------------------------- decisiones
def test_baneo_desde_un_reporte_de_persona(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    rid = _reportar(paciente, pid)

    r = admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "baneo", "nota": "Reincidente"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "Resuelto" and r.json()["resolucion"]["decision"] == "baneo"
    assert r.json()["resolucion"]["nota"] == "Reincidente" and r.json()["resolucion"]["resuelto_por"] == "Admin Prueba"
    assert _login(client, "est@test.cl").status_code == 403
    assert paciente.get(f"/api/postulaciones/{pid}").json()["estado"] == "Cancelada"
    # Quien reportó se entera de que se revisó, sin detalles.
    avisos = [a["texto"] for a in paciente.get("/api/avisos").json()]
    assert any("Revisamos tu reporte" in a and "medidas" in a for a in avisos)


def test_suspension_exige_dias_y_vuelve_sola(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    rid = _reportar(paciente, pid)

    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "suspension"}).status_code == 422
    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "suspension", "dias": 0}).status_code == 422
    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "suspension", "dias": 91}).status_code == 422

    r = admin.post(f"/api/admin/reportes/{rid}/resolver",
                   json={"decision": "suspension", "dias": 7, "mensaje": "Cuida el trato con los pacientes"})
    assert r.status_code == 200, r.text
    assert r.json()["resolucion"]["dias"] == 7 and r.json()["reportado"]["estado_cuenta"] == "suspendido"

    login = _login(client, "est@test.cl")
    assert login.status_code == 403
    assert "suspendida hasta el" in login.json()["detail"] and "Cuida el trato" in login.json()["detail"]

    # Pasado el time-out, la cuenta vuelve sola.
    db = SessionLocal()
    try:
        db.get(models.EstadoCuenta, estudiante.id).suspendido_hasta = ahora() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert _login(client, "est@test.cl").status_code == 200


def test_la_suspension_deja_las_advertencias_en_cero(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    _banear_por_insultos(estudiante, pid)
    rid = admin.get("/api/admin/reportes").json()[0]["id"]
    r = admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "suspension", "dias": 3})
    assert r.json()["reportado"]["advertencias"] == 0


def test_descartar_un_baneo_automatico_reactiva_la_cuenta_y_avisa_a_ambos(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    _banear_por_insultos(estudiante, pid)
    paciente.get("/api/avisos")          # el aviso del cierre ya se vio
    rid = admin.get("/api/admin/reportes").json()[0]["id"]

    r = admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "descartar"})
    assert r.status_code == 200 and r.json()["reportado"]["estado_cuenta"] == "activo"
    assert r.json()["reportado"]["advertencias"] == 0

    assert _login(client, "est@test.cl").status_code == 200
    # Lo cancelado NO se restituye...
    assert paciente.get(f"/api/postulaciones/{pid}").json()["estado"] == "Cancelada"
    # ...pero los dos reciben un aviso.
    de_paciente = [a["texto"] for a in paciente.get("/api/avisos").json()]
    assert any("su cuenta se reactivó" in a for a in de_paciente)
    est = crear_sesion_de(client, "est@test.cl")
    assert any("reactivada" in a["texto"] for a in est.get("/api/avisos").json())


def crear_sesion_de(client, correo):
    from tests.conftest import Sesion

    token = _login(client, correo).json()["access_token"]
    return Sesion(client, 0, {"Authorization": f"Bearer {token}"}, correo)


def test_descartar_un_reporte_de_persona_no_toca_la_cuenta(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    rid = _reportar(paciente, pid)
    r = admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "descartar"})
    assert r.status_code == 200 and r.json()["reportado"]["estado_cuenta"] == "activo"
    assert _login(client, "est@test.cl").status_code == 200
    avisos = [a["texto"] for a in paciente.get("/api/avisos").json()]
    assert any("no encontramos un incumplimiento" in a for a in avisos)


def test_un_reporte_resuelto_no_se_resuelve_dos_veces(client, paciente, estudiante):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    rid = _reportar(paciente, pid)
    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "descartar"}).status_code == 200
    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "baneo"}).status_code == 409
    assert admin.post(f"/api/admin/reportes/{rid}/resolver", json={"decision": "otra"}).status_code == 422
    assert admin.get("/api/admin/reportes").json() == []
    assert [r["id"] for r in admin.get("/api/admin/reportes?estado=Resuelto").json()] == [rid]


# ---------------------------------------------------------------- cuentas
def test_cuentas_y_levantar_sancion(client, paciente, estudiante, estudiante2):
    admin = _crear_admin(client)
    pid = _vinculo(paciente, estudiante)
    _banear_por_insultos(estudiante, pid)

    todas = admin.get("/api/admin/cuentas").json()
    assert todas[0]["id"] == estudiante.id and todas[0]["estado_cuenta"] == "baneado"   # sancionadas primero
    assert todas[0]["reportes_recibidos"] == 1 and todas[0]["advertencias"] == 3
    assert {c["rol"] for c in todas} == {"estudiante", "paciente"}                      # nunca aparece un admin
    assert [c["id"] for c in admin.get("/api/admin/cuentas?estado=baneado").json()] == [estudiante.id]
    assert [c["id"] for c in admin.get("/api/admin/cuentas?q=Sofía").json()] == [estudiante2.id]
    assert admin.get("/api/admin/cuentas?estado=otro").status_code == 422

    assert admin.post(f"/api/admin/cuentas/{estudiante2.id}/levantar-sancion").status_code == 409
    r = admin.post(f"/api/admin/cuentas/{estudiante.id}/levantar-sancion")
    assert r.status_code == 200 and r.json()["estado_cuenta"] == "activo" and r.json()["advertencias"] == 0
    assert _login(client, "est@test.cl").status_code == 200
    assert admin.post("/api/admin/cuentas/9999/levantar-sancion").status_code == 404


# ---------------------------------------------------------------- acceso al panel
def test_la_pagina_del_panel_se_sirve_y_el_admin_inicia_sesion(client):
    assert client.get("/admin").status_code == 200
    assert "Administración" in client.get("/admin").text
    _crear_admin(client)
    login = _login(client, "admin@test.cl")
    assert login.status_code == 200 and login.json()["rol"] == "admin"   # el login devuelve el rol para redirigir


def test_el_registro_publico_sigue_sin_crear_admins(client):
    r = client.post("/api/registro", data={"nombre_completo": "Intruso Pérez", "rut": "11.111.111-1",
                    "correo": "intruso@test.cl", "contrasena": "123456", "rol": "admin"})
    assert r.status_code == 400 and r.json()["detail"] == "Rol inválido"
