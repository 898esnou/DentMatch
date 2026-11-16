"""Bloquear / desbloquear en el chat, mensajes inapropiados visibles solo si se piden, y casos con postulación pendiente."""
from tests.conftest import SOLICITUD
from tests.test_chat import _enviar, _vinculo


# ---------------------------------------------------------------- bloquear
def test_bloquear_deja_el_chat_en_solo_lectura_y_solo_quien_bloqueo_desbloquea(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid, "Hola, ¿cómo estás?")

    r = paciente.post(f"/api/chat/{pid}/bloquear")
    assert r.status_code == 200, r.text
    assert r.json()["bloqueada"] is True and r.json()["bloqueada_por_mi"] is True
    assert r.json()["puede_escribir"] is False and r.json()["se_borra_el"] is not None

    for sesion in (paciente, estudiante):
        e = _enviar(sesion, pid, "¿Sigues ahí?")
        assert e.status_code == 409 and "bloqueada" in e.json()["detail"]

    conv = estudiante.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]
    assert conv["bloqueada"] is True and conv["bloqueada_por_mi"] is False
    assert estudiante.post(f"/api/chat/{pid}/desbloquear").status_code == 403
    avisos = [a["texto"] for a in estudiante.get("/api/avisos").json()]
    assert any("bloqueó la conversación" in a for a in avisos)

    r = paciente.post(f"/api/chat/{pid}/desbloquear")
    assert r.status_code == 200 and r.json()["bloqueada"] is False and r.json()["puede_escribir"] is True
    assert _enviar(estudiante, pid, "Gracias").status_code == 201


def test_validaciones_de_bloquear(paciente, paciente2, estudiante):
    pid = _vinculo(paciente, estudiante)
    assert paciente.post(f"/api/chat/{pid}/desbloquear").status_code == 409   # no está bloqueada
    assert paciente.post(f"/api/chat/{pid}/bloquear").status_code == 200
    assert paciente.post(f"/api/chat/{pid}/bloquear").status_code == 409      # ya lo está
    assert paciente2.post(f"/api/chat/{pid}/bloquear").status_code == 404     # ajena

    pid2 = _vinculo(paciente, estudiante)
    paciente.post(f"/api/postulaciones/{pid2}/cancelar")
    assert paciente.post(f"/api/chat/{pid2}/bloquear").status_code == 409     # ya cerrada


def test_se_puede_reportar_en_un_chat_bloqueado(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("uno", "dos", "tres"):
        _enviar(estudiante, pid, texto)
    paciente.post(f"/api/chat/{pid}/bloquear")
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["puede_reportar"] is True
    assert paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "Me incomodó la conversación"}).status_code == 201


# ---------------------------------------------------------------- mensajes inapropiados
def test_quien_recibe_puede_leer_los_mensajes_que_causaron_el_baneo(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid, "Hola, ¿cómo estás?")
    # Antes del baneo no se muestra nada: los mensajes bloqueados nunca le llegaron.
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes_inapropiados"] == []

    _enviar(estudiante, pid, "idiota")
    _enviar(estudiante, pid, "imbécil")
    assert _enviar(estudiante, pid, "te voy a matar").status_code == 403   # tercera advertencia: baneo

    hilo = paciente.get(f"/api/chat/{pid}/mensajes").json()
    assert hilo["conversacion"]["cerrada_por_moderacion"] is True
    assert [m["contenido"] for m in hilo["mensajes_inapropiados"]] == ["idiota", "imbécil", "te voy a matar"]
    assert {m["categoria"] for m in hilo["mensajes_inapropiados"]} == {"insulto"}
    # Los mensajes normales siguen siendo solo los enviados de verdad.
    assert [m["contenido"] for m in hilo["mensajes"]] == ["Hola, ¿cómo estás?"]


def test_los_mensajes_fuera_de_tema_no_se_muestran_como_inapropiados(paciente, estudiante, monkeypatch):
    from app import moderacion
    pid = _vinculo(paciente, estudiante)
    monkeypatch.setattr(moderacion, "moderar", lambda *a, **k: moderacion.Resultado("fuera_de_tema", "ia"))
    assert _enviar(estudiante, pid, "¿Me ayudas con mi tarea de historia?").status_code == 422
    monkeypatch.undo()
    for palabra in ("idiota", "imbécil", "te voy a matar"):
        _enviar(estudiante, pid, palabra)
    contenidos = [m["contenido"] for m in paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes_inapropiados"]]
    assert "¿Me ayudas con mi tarea de historia?" not in contenidos and len(contenidos) == 3


# ---------------------------------------------------------------- casos con postulación pendiente
def test_caso_con_postulacion_pendiente_indica_si_el_estudiante_puede_responder(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()

    # Postuló el estudiante: puede cancelarla, no aceptarla.
    estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]})
    caso = next(c for c in estudiante.get("/api/casos").json() if c["id"] == sol["id"])
    assert caso["mi_postulacion_estado"] == "Pendiente" and caso["mi_postulacion_puede_responder"] is False
    assert caso["mi_postulacion_id"] is not None


def test_caso_que_el_paciente_solicito_al_estudiante_se_puede_responder(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    r = paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"], "estudiante_id": estudiante.id})
    assert r.status_code == 201, r.text
    caso = next(c for c in estudiante.get("/api/casos").json() if c["id"] == sol["id"])
    assert caso["mi_postulacion_estado"] == "Pendiente" and caso["mi_postulacion_puede_responder"] is True
