"""Chat de coordinación: una conversación por postulación, con historial de 30 días al cerrar."""
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.servicios import ahora
from tests.conftest import SOLICITUD, marcar_estado_verificacion


def _vinculo(paciente, estudiante, aceptar=True):
    """Crea una solicitud, el estudiante postula y (opcional) el paciente acepta. Devuelve el id."""
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    post = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    if aceptar:
        r = paciente.post(f"/api/postulaciones/{post['id']}/responder", json={"accion": "aceptar"})
        assert r.status_code == 200, r.text
    return post["id"]


def _enviar(sesion, pid, texto="Hola"):
    return sesion.post(f"/api/chat/{pid}/mensajes", json={"contenido": texto})


def _envejecer_cierre(pid, dias):
    """Atrasa la fecha de cierre de una postulación cancelada (atajo para probar el borrado)."""
    db = SessionLocal()
    try:
        db.get(models.Postulacion, pid).fecha_respuesta = ahora() - timedelta(days=dias)
        db.commit()
    finally:
        db.close()


def test_no_hay_chat_hasta_que_se_acepta(paciente, estudiante):
    pid = _vinculo(paciente, estudiante, aceptar=False)
    assert paciente.get("/api/chat/conversaciones").json() == []
    assert _enviar(estudiante, pid).status_code == 409


def test_conversacion_con_no_leidos_y_visto(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    r = _enviar(paciente, pid, "Hola, ¿cuánto cuesta?")
    assert r.status_code == 201 and r.json()["mio"] is True
    _enviar(estudiante, pid, "El martes a las 15:30 te sirve?")

    conv = estudiante.get("/api/chat/conversaciones").json()
    assert len(conv) == 1 and conv[0]["no_leidos"] == 1 and conv[0]["puede_escribir"] is True
    assert conv[0]["otra_parte"]["nombre"] == "Camila Soto M." and conv[0]["se_borra_el"] is None

    hilo = estudiante.get(f"/api/chat/{pid}/mensajes").json()
    assert [m["mio"] for m in hilo["mensajes"]] == [False, True]
    assert estudiante.get("/api/chat/conversaciones").json()[0]["no_leidos"] == 0
    # El mensaje de la paciente quedó "visto" porque el estudiante abrió el hilo.
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"][0]["leido"] is True


def test_solo_los_participantes_acceden(paciente, paciente2, estudiante, estudiante2):
    pid = _vinculo(paciente, estudiante)
    for ajeno in (paciente2, estudiante2):
        assert ajeno.get(f"/api/chat/{pid}/mensajes").status_code == 404
        assert _enviar(ajeno, pid).status_code == 404
        assert ajeno.get("/api/chat/conversaciones").json() == []


def test_validaciones_del_mensaje(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    assert _enviar(paciente, pid, "   ").status_code == 422
    assert _enviar(paciente, pid, "x" * 1001).status_code == 422


def test_estudiante_sin_verificar_no_escribe(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    marcar_estado_verificacion(estudiante.id, "No verificado")
    assert _enviar(estudiante, pid).status_code == 403


def test_al_cancelar_queda_solo_lectura_y_avisa_cuando_se_borra(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid)
    paciente.post(f"/api/postulaciones/{pid}/cancelar")

    assert _enviar(paciente, pid, "¿sigue en pie?").status_code == 409
    hilo = paciente.get(f"/api/chat/{pid}/mensajes").json()
    assert len(hilo["mensajes"]) == 1  # el historial se conserva
    assert hilo["conversacion"]["puede_escribir"] is False
    assert hilo["conversacion"]["se_borra_el"] is not None


def test_al_completar_queda_solo_lectura(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(estudiante, pid)
    assert estudiante.post(f"/api/postulaciones/{pid}/completar").status_code == 200
    conv = paciente.get("/api/chat/conversaciones").json()[0]
    assert conv["puede_escribir"] is False and conv["se_borra_el"] is not None
    assert _enviar(paciente, pid).status_code == 409


def test_el_historial_se_borra_a_los_30_dias_del_cierre(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid)
    paciente.post(f"/api/postulaciones/{pid}/cancelar")

    _envejecer_cierre(pid, dias=29)  # todavía dentro del plazo
    assert len(paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"]) == 1

    _envejecer_cierre(pid, dias=31)  # plazo cumplido: se borra
    assert paciente.get("/api/chat/conversaciones").json() == []
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"] == []


def test_una_conversacion_abierta_nunca_se_borra(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid)
    assert len(paciente.get("/api/chat/conversaciones").json()) == 1
    assert len(paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"]) == 1
