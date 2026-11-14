"""Límite de 500 caracteres en la solicitud, y archivar / reabrir una conversación del chat."""
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.servicios import ahora
from tests.conftest import SOLICITUD
from tests.test_chat import _enviar, _vinculo


# ---------------------------------------------------------------- 500 caracteres
def test_la_descripcion_de_la_solicitud_tiene_un_maximo_de_500_caracteres(paciente):
    justo = {**SOLICITUD, "descripcion": "a" * 500}
    r = paciente.post("/api/solicitudes", json=justo)
    assert r.status_code == 201, r.text

    demasiado = {**SOLICITUD, "descripcion": "a" * 501}
    r = paciente.post("/api/solicitudes", json=demasiado)
    assert r.status_code == 422

    # También al editar.
    sid = paciente.post("/api/solicitudes", json=SOLICITUD).json()["id"]
    assert paciente.patch(f"/api/solicitudes/{sid}", json={"descripcion": "b" * 500}).status_code == 200
    assert paciente.patch(f"/api/solicitudes/{sid}", json={"descripcion": "b" * 501}).status_code == 422


def test_editar_la_clasificacion_de_una_solicitud_abierta(paciente):
    """El botón «Editar» del portal usa este endpoint: cambia el área (la clasificación)."""
    sid = paciente.post("/api/solicitudes", json=SOLICITUD).json()["id"]
    r = paciente.patch(f"/api/solicitudes/{sid}", json={"area": "cirugia", "urgente": False, "comuna": None})
    assert r.status_code == 200
    assert r.json()["area"] == "cirugia" and r.json()["urgente"] is False and r.json()["comuna"] is None
    assert paciente.patch(f"/api/solicitudes/{sid}", json={"area": "inventada"}).status_code == 422


# ---------------------------------------------------------------- archivar conversación
def _archivo(pid):
    db = SessionLocal()
    try:
        return db.get(models.ConversacionArchivada, pid)
    finally:
        db.close()


def test_archivar_deja_el_chat_en_solo_lectura_para_las_dos_personas(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid, "Hola, ¿cuándo nos vemos?")

    r = paciente.post(f"/api/chat/{pid}/archivar")
    assert r.status_code == 200, r.text
    assert r.json()["archivada"] is True and r.json()["archivada_por_mi"] is True
    assert r.json()["puede_escribir"] is False and r.json()["se_borra_el"] is not None

    # Ninguna de las dos puede escribir, y el mensaje lo explica.
    for sesion in (paciente, estudiante):
        e = _enviar(sesion, pid, "¿Sigues ahí?")
        assert e.status_code == 409 and "archivada" in e.json()["detail"]

    # La otra persona lo ve archivado, pero no puede reabrirlo.
    conv = estudiante.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]
    assert conv["archivada"] is True and conv["archivada_por_mi"] is False
    assert estudiante.post(f"/api/chat/{pid}/reabrir").status_code == 403
    # Se le avisa (sin detalles), y el historial se conserva.
    avisos = [a["texto"] for a in estudiante.get("/api/avisos").json()]
    assert any("archivó la conversación" in a for a in avisos)
    assert len(estudiante.get(f"/api/chat/{pid}/mensajes").json()["mensajes"]) == 1


def test_archivar_no_cambia_la_postulacion_ni_las_citas(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    paciente.post(f"/api/chat/{pid}/archivar")
    assert paciente.get(f"/api/postulaciones/{pid}").json()["estado"] == "Aceptada"


def test_quien_archivo_puede_reabrir(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    estudiante.post(f"/api/chat/{pid}/archivar")
    r = estudiante.post(f"/api/chat/{pid}/reabrir")
    assert r.status_code == 200 and r.json()["archivada"] is False and r.json()["puede_escribir"] is True
    assert _archivo(pid) is None
    assert _enviar(paciente, pid, "Gracias por reabrir").status_code == 201
    avisos = [a["texto"] for a in paciente.get("/api/avisos").json()]
    assert any("reabrió la conversación" in a for a in avisos)


def test_validaciones_de_archivar_y_reabrir(paciente, paciente2, estudiante):
    pid = _vinculo(paciente, estudiante)
    assert paciente.post(f"/api/chat/{pid}/reabrir").status_code == 409          # no está archivada
    assert paciente.post(f"/api/chat/{pid}/archivar").status_code == 200
    assert paciente.post(f"/api/chat/{pid}/archivar").status_code == 409         # ya lo está
    assert paciente2.post(f"/api/chat/{pid}/archivar").status_code == 404        # ajena
    assert paciente2.post(f"/api/chat/{pid}/reabrir").status_code == 404

    # Una conversación ya cerrada (postulación cancelada) no se puede archivar.
    pid2 = _vinculo(paciente, estudiante)
    paciente.post(f"/api/postulaciones/{pid2}/cancelar")
    assert paciente.post(f"/api/chat/{pid2}/archivar").status_code == 409


def test_chat_archivado_aparece_en_la_lista_aunque_no_tenga_mensajes(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    paciente.post(f"/api/chat/{pid}/archivar")
    lista = estudiante.get("/api/chat/conversaciones").json()
    assert [c["postulacion_id"] for c in lista] == [pid] and lista[0]["archivada"] is True


def test_el_historial_archivado_se_borra_a_los_30_dias(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid, "Hola")
    paciente.post(f"/api/chat/{pid}/archivar")
    db = SessionLocal()
    try:
        db.get(models.ConversacionArchivada, pid).fecha = ahora() - timedelta(days=31)
        db.commit()
    finally:
        db.close()
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"] == []


def test_se_puede_reportar_en_un_chat_archivado(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("Hola", "Hola, ¿qué tal?", "Todo bien, ¿y tú?"):
        _enviar(paciente if texto != "Hola, ¿qué tal?" else estudiante, pid, texto)
    paciente.post(f"/api/chat/{pid}/archivar")
    r = paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "Me incomodó la conversación"})
    assert r.status_code == 201, r.text
