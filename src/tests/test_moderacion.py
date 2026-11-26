"""Moderación del chat (Épica 5): reglas, IA simulada, advertencias, baneo, reportes y avisos."""
import json

import pytest

from app import models, moderacion
from app.database import SessionLocal
from tests.conftest import SOLICITUD
from tests.test_chat import _enviar, _vinculo


# ---------------------------------------------------------------- reglas (funciones puras)
@pytest.mark.parametrize("texto", [
    "Hola, ¿te sirve el martes a las 15:30?",
    "Me duele mucho la muela y tengo sangrado de la encía",
    "Necesito una extracción y me da miedo la anestesia",
    "La restauración quedó bonita, gracias",
    "Estoy infeliz con el resultado, ¿se puede corregir?",
    "Estas citas son los lunes, ¿verdad?",
    "Llevo 15.30 en mi reloj, llego en 10 minutos",
    "Hola, te voy a buscar a la entrada de la clínica",
    "Te voy a encontrar en el box 3",
])
def test_reglas_dejan_pasar_mensajes_normales(texto):
    assert moderacion.evaluar_con_reglas(texto).permitido


@pytest.mark.parametrize("texto", [
    "eres un idiota",
    "Qué imbécil eres",
    "puuuuta que eres lento",
    "p.u.t.a",
    "ctm",
    "te voy a matar",
    "HIJO DE PUTA",
])
def test_reglas_detectan_insultos_y_amenazas(texto):
    r = moderacion.evaluar_con_reglas(texto)
    assert r.categoria == "insulto" and r.fuente == "reglas" and r.cuenta_como_advertencia


@pytest.mark.parametrize("texto", [
    "estas muy buena",
    "Te ves sexy",
    "mándame una foto tuya sin ropa",
    "ven a mi casa esta noche",
    "quieres ser mi novia",
])
def test_reglas_detectan_insinuaciones(texto):
    r = moderacion.evaluar_con_reglas(texto)
    assert r.categoria == "acoso" and r.cuenta_como_advertencia


def test_fuera_de_tema_no_suma_advertencia():
    assert not moderacion.Resultado("fuera_de_tema", "ia").cuenta_como_advertencia


def test_interpretar_respuesta_de_gemini():
    assert moderacion.interpretar_respuesta('{"categoria": "acoso"}') == "acoso"
    assert moderacion.interpretar_respuesta('{"categoria": "ok"}') is None
    assert moderacion.interpretar_respuesta('{"categoria": "inventada"}') is None
    assert moderacion.interpretar_respuesta("esto no es json") is None
    assert moderacion.interpretar_respuesta("[]") is None


def test_sin_clave_o_apagada_la_ia_deja_pasar(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_MODERACION", raising=False)
    assert not moderacion.ia_habilitada()
    assert moderacion.moderar("vendo zapatillas baratas, escríbeme").permitido

    monkeypatch.setenv("GEMINI_API_KEY_MODERACION", "clave-falsa")
    monkeypatch.setenv("MODERACION_IA", "0")
    assert not moderacion.ia_habilitada()


def test_si_gemini_falla_el_mensaje_pasa(monkeypatch):
    monkeypatch.setenv("MODERACION_IA", "1")
    monkeypatch.setenv("GEMINI_API_KEY_MODERACION", "clave-falsa")

    def explota():
        raise RuntimeError("sin internet")

    monkeypatch.setattr(moderacion, "_obtener_cliente", explota)
    assert moderacion.clasificar_con_ia("vendo zapatillas baratas", []).permitido


def test_moderar_usa_la_ia_solo_si_las_reglas_no_dicen_nada(monkeypatch):
    llamadas = []

    def falsa(texto, contexto):
        llamadas.append(texto)
        return moderacion.Resultado("fuera_de_tema", "ia")

    monkeypatch.setattr(moderacion, "clasificar_con_ia", falsa)
    assert moderacion.moderar("eres un idiota").fuente == "reglas" and llamadas == []
    assert moderacion.moderar("compra criptomonedas ya").categoria == "fuera_de_tema" and llamadas


# ---------------------------------------------------------------- chat con moderación
def _advertencias(usuario_id):
    db = SessionLocal()
    try:
        return db.query(models.Advertencia).filter(models.Advertencia.usuario_id == usuario_id).count()
    finally:
        db.close()


def test_mensaje_bloqueado_no_le_llega_al_receptor(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    r = _enviar(estudiante, pid, "eres un idiota")
    assert r.status_code == 422
    assert "no se envió" in r.json()["detail"] and "Advertencia 1 de 3" in r.json()["detail"]
    # Nada quedó guardado como mensaje: la paciente no ve nada.
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["mensajes"] == []
    assert _advertencias(estudiante.id) == 1


def test_receptor_recibe_recordatorio_de_reportar_una_vez(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(estudiante, pid, "te voy a matar")
    # El emisor no ve ese recordatorio.
    assert estudiante.get(f"/api/chat/{pid}/mensajes").json()["aviso_moderacion"] is None
    hilo = paciente.get(f"/api/chat/{pid}/mensajes").json()
    assert "Reportar" in hilo["aviso_moderacion"]
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["aviso_moderacion"] is None  # solo una vez


def test_fuera_de_tema_avisa_pero_no_suma(paciente, estudiante, monkeypatch):
    monkeypatch.setattr(moderacion, "clasificar_con_ia", lambda t, c: moderacion.Resultado("fuera_de_tema", "ia"))
    pid = _vinculo(paciente, estudiante)
    r = _enviar(estudiante, pid, "compra mis productos de belleza")
    assert r.status_code == 422 and "Advertencia" not in r.json()["detail"]
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["aviso_moderacion"] is None


def test_tres_advertencias_banean_y_crean_reporte_automatico(client, paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    assert _enviar(estudiante, pid, "idiota").status_code == 422
    assert _enviar(estudiante, pid, "imbécil").status_code == 422
    r = _enviar(estudiante, pid, "te voy a matar")
    assert r.status_code == 403 and "suspendida" in r.json()["detail"]

    # Ya no puede usar la API ni iniciar sesión.
    assert estudiante.get("/api/me").status_code == 403
    login = client.post("/api/login", json={"correo": "est@test.cl", "contrasena": "123456"})
    assert login.status_code == 403 and "suspendida" in login.json()["detail"]

    db = SessionLocal()
    try:
        reporte = db.query(models.Reporte).one()
        assert (reporte.origen, reporte.estado, reporte.reportado_id) == ("automatico", "Pendiente", estudiante.id)
        assert reporte.reportante_id is None
        evidencia = json.loads(reporte.evidencia)
        assert [m["contenido"] for m in evidencia["mensajes_bloqueados"]] == ["idiota", "imbécil", "te voy a matar"]
    finally:
        db.close()


def test_baneo_cancela_vinculos_y_avisa_a_la_contraparte(paciente, paciente2, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("idiota", "imbécil", "te voy a matar"):
        _enviar(estudiante, pid, texto)

    assert paciente.get(f"/api/postulaciones/{pid}").json()["estado"] == "Cancelada"
    # La solicitud de la paciente volvió a estar abierta y el chat quedó cerrado.
    sol = paciente.get("/api/solicitudes").json()[0]
    assert sol["estado"] == "Abierta"
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]["puede_escribir"] is False
    # Aviso (sin contar el motivo) y, una vez visto, desaparece.
    avisos = paciente.get("/api/avisos").json()
    assert len(avisos) == 1 and "chat ha sido detenido" in avisos[0]["texto"]
    assert "idiota" not in avisos[0]["texto"] and "suspendid" not in avisos[0]["texto"].lower()
    # En el propio chat, la contraparte ve por qué se detuvo y qué hacer.
    conv = paciente.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]
    assert conv["cerrada_por_moderacion"] is True and conv["puede_escribir"] is False
    assert "normas de convivencia" in conv["mensaje_cierre"] and "otro estudiante" in conv["mensaje_cierre"]
    assert "Matías" not in conv["mensaje_cierre"]  # no se nombra a nadie
    assert paciente.get("/api/avisos").json() == []
    # El estudiante baneado ya no aparece ni se le puede solicitar.
    assert paciente.get("/api/estudiantes").json() == []
    assert paciente.get(f"/api/estudiantes/{estudiante.id}").status_code == 404
    otra = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    r = paciente.post("/api/postulaciones", json={"solicitud_id": otra["id"], "estudiante_id": estudiante.id})
    assert r.status_code == 409


def test_baneo_de_paciente_cierra_sus_solicitudes_y_avisa_al_estudiante(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("idiota", "imbécil", "te voy a matar"):
        _enviar(paciente, pid, texto)

    assert estudiante.get(f"/api/postulaciones/{pid}").json()["estado"] == "Cancelada"
    assert estudiante.get("/api/casos").json() == []  # su solicitud ya no se ofrece
    avisos = estudiante.get("/api/avisos").json()
    assert len(avisos) == 1 and "chat ha sido detenido" in avisos[0]["texto"]
    conv = estudiante.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]
    assert conv["cerrada_por_moderacion"] is True and "otro caso" in conv["mensaje_cierre"]


def test_las_advertencias_vencen_a_los_30_dias(paciente, estudiante):
    from datetime import timedelta

    from app.servicios import ahora

    pid = _vinculo(paciente, estudiante)
    _enviar(estudiante, pid, "idiota")
    _enviar(estudiante, pid, "imbécil")
    db = SessionLocal()
    try:
        for a in db.query(models.Advertencia).all():
            a.fecha = ahora() - timedelta(days=31)
        db.commit()
    finally:
        db.close()
    r = _enviar(estudiante, pid, "estupido")  # las anteriores ya no cuentan: esta es la 1ª
    assert r.status_code == 422 and "Advertencia 1 de 3" in r.json()["detail"]


# ---------------------------------------------------------------- reportar
def test_reportar_se_habilita_tras_unos_mensajes(paciente, estudiante, paciente2):
    pid = _vinculo(paciente, estudiante)
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["puede_reportar"] is False
    r = paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "Me escribió cosas raras"})
    assert r.status_code == 409  # todavía no hay mensajes suficientes

    _enviar(paciente, pid, "Hola")
    _enviar(estudiante, pid, "Hola, ¿cómo estás?")
    _enviar(paciente, pid, "Bien, ¿el martes te sirve?")
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["puede_reportar"] is True

    r = paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "Me escribió cosas raras"})
    assert r.status_code == 201, r.text
    # No se puede reportar dos veces mientras el primero siga pendiente.
    assert paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "Otra vez lo mismo"}).status_code == 409
    assert paciente.get(f"/api/chat/{pid}/mensajes").json()["puede_reportar"] is False
    # Un tercero no puede reportar una conversación ajena.
    assert paciente2.post(f"/api/chat/{pid}/reportar", json={"motivo": "Algo que vi"}).status_code == 404

    db = SessionLocal()
    try:
        reporte = db.query(models.Reporte).one()
        assert (reporte.origen, reporte.reportante_id, reporte.reportado_id) == ("usuario", paciente.id, estudiante.id)
        assert len(json.loads(reporte.evidencia)["mensajes"]) == 3  # copia de la conversación
    finally:
        db.close()


def test_el_motivo_del_reporte_es_obligatorio(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("Hola", "Hola", "Hola"):
        _enviar(paciente, pid, texto)
    assert paciente.post(f"/api/chat/{pid}/reportar", json={"motivo": "x"}).status_code == 422


def test_chat_detenido_se_muestra_aunque_no_tenga_mensajes(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    for texto in ("idiota", "imbécil", "te voy a matar"):
        _enviar(estudiante, pid, texto)
    # Ningún mensaje llegó a guardarse, pero la paciente igual ve el chat detenido en su lista.
    lista = paciente.get("/api/chat/conversaciones").json()
    assert [c["postulacion_id"] for c in lista] == [pid] and lista[0]["cerrada_por_moderacion"] is True


def test_un_chat_cerrado_normalmente_no_dice_que_fue_moderacion(paciente, estudiante):
    pid = _vinculo(paciente, estudiante)
    _enviar(paciente, pid, "Hola")
    assert paciente.post(f"/api/postulaciones/{pid}/cancelar").status_code == 200
    conv = estudiante.get(f"/api/chat/{pid}/mensajes").json()["conversacion"]
    assert conv["cerrada_por_moderacion"] is False and conv["mensaje_cierre"] is None


def test_los_chats_son_solo_de_quienes_participan_tambien_con_moderacion(client, paciente, paciente2, estudiante):
    from tests.test_admin import _crear_admin

    pid = _vinculo(paciente, estudiante)
    for texto in ("idiota", "imbécil", "te voy a matar"):
        _enviar(estudiante, pid, texto)
    # Un tercero no ve el chat ni su cierre, y un admin tampoco lo abre por la vía del chat
    # (los reportes llevan su propia copia de la evidencia).
    assert paciente2.get(f"/api/chat/{pid}/mensajes").status_code == 404
    assert paciente2.get("/api/chat/conversaciones").json() == []
    admin = _crear_admin(client)
    assert admin.get(f"/api/chat/{pid}/mensajes").status_code == 403
    assert admin.get("/api/chat/conversaciones").status_code == 403
