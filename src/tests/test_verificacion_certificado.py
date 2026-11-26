"""Lectura automática del certificado de alumno regular de la UNAB (QR)."""
from datetime import date

import pytest

from app import verificacion_certificado as vc
from app.verificacion_certificado import ResultadoVerificacion, evaluar_datos
from tests.conftest import PDF_VALIDO
from tests.test_verificacion import _subir

HOY = date(2026, 9, 1)  # segundo semestre 2026: vale lo emitido de julio a diciembre
DATOS = {
    "RUT": "20.923.202-2", "NOMBRE": "MONSERRAT ALEJANDRA", "APELLIDOS": "CANALES OPORTUS",
    "CARRERA": "UNAB19910 - ODONTOLOGÍA", "ESTADO": "ES ALUMNO", "FECHA EMISION": "20-07-2026",
}
PAGINA = """<dl><dt>Rut:</dt><dd>20.923.202-2</dd><dt>Apellidos:</dt><dd>CANALES OPORTUS</dd>
<dt>Nombre:</dt><dd>MONSERRAT ALEJANDRA</dd><dt>Carrera:</dt><dd>UNAB19910 - ODONTOLOG&Iacute;A</dd>
<dt>Estado:</dt><dd>ES ALUMNO</dd><dt>Fecha Emisi&oacute;n:</dt><dd>20-07-2026</dd></dl>"""


def _evaluar(nombre="Monserrat Canales", documento="20923202-2", **cambios):
    return evaluar_datos({**DATOS, **cambios}, nombre, documento, HOY)


def test_aprueba_cuando_todo_coincide():
    assert _evaluar() == ResultadoVerificacion(True, fecha_emision=date(2026, 7, 20))


def test_el_dia_de_emision_da_lo_mismo_dentro_del_semestre():
    # emitido el 1 o el 31 de julio: mismo semestre
    assert _evaluar(**{"FECHA EMISION": "01-07-2026"}).aprobada is True
    assert _evaluar(**{"FECHA EMISION": "31-08-2026"}).aprobada is True


def test_rechaza_otro_rut():
    r = _evaluar(documento="11111111-1")
    assert r.aprobada is False and "RUT" in r.motivo


@pytest.mark.parametrize("cambio,texto", [
    ({"ESTADO": "NO ES ALUMNO"}, "alumno regular"),
    ({"CARRERA": "UNAB1 - DERECHO"}, "Odontología"),
    ({"FECHA EMISION": "30-06-2026"}, "semestre anterior"),
    ({"FECHA EMISION": "15-01-2026"}, "semestre anterior"),
    ({"FECHA EMISION": "20-10-2025"}, "semestre anterior"),  # mismo semestre (jul-dic) pero de otro año
])
def test_rechaza_con_motivo(cambio, texto):
    r = _evaluar(**cambio)
    assert r.aprobada is False and texto in r.motivo


def test_nombre_distinto_o_datos_ilegibles_van_a_revision_manual():
    assert _evaluar(nombre="Pepe Gómez") is None
    assert _evaluar(**{"FECHA EMISION": "pronto"}) is None
    assert _evaluar(**{"FECHA EMISION": "01-12-2026"}) is None  # fecha futura
    assert evaluar_datos({}, "Monserrat Canales", "20923202-2", HOY) is None


def test_nombre_con_tildes_y_orden_distinto_coincide():
    assert _evaluar(nombre="Oportus Canales, Monserrat").aprobada is True


def test_extrae_datos_de_la_pagina():
    datos = vc._extraer_datos(PAGINA)
    assert datos["RUT"] == "20.923.202-2" and datos["CARRERA"].endswith("ODONTOLOGÍA")
    assert datos["FECHA EMISION"] == "20-07-2026" and datos["ESTADO"] == "ES ALUMNO"


@pytest.mark.parametrize("qr", [
    "http://127.0.0.1/qr.php?f=1&i=2",
    "https://certificados.unab.cl.evil.com/qr.php?f=1&i=2",
    "https://evil.com/qr.php?f=1&i=2",
    "https://certificados.unab.cl/qr.php?f=1&i=../etc",
    "https://certificados.unab.cl/qr.php",
    "no es una url",
])
def test_ssrf_solo_se_acepta_el_dominio_oficial(qr):
    assert vc._url_oficial(qr) is None


def test_la_url_se_reconstruye_con_el_dominio_fijo():
    assert vc._url_oficial("http://certificados.unab.cl/otra.php?f=3852350&i=209232022&x=1") == (
        "https://certificados.unab.cl/qr.php?f=3852350&i=209232022"
    )


def test_sin_qr_legible_queda_para_revision_manual():
    assert vc.verificar_automaticamente(PDF_VALIDO, "application/pdf", "Ana Pérez", "11111111-1") is None


def test_flujo_completo_aprueba_y_activa(estudiante_nuevo, monkeypatch):
    monkeypatch.setattr(vc, "_leer_qr", lambda *a: "https://certificados.unab.cl/qr.php?f=1&i=2")
    monkeypatch.setattr(vc, "_descargar_pagina", lambda url: PAGINA)
    # la cuenta de prueba tiene otro RUT/nombre: se ajusta el certificado a ella
    monkeypatch.setattr(vc, "_descargar_pagina", lambda url: PAGINA.replace("20.923.202-2", "15.555.555-6").replace(
        "MONSERRAT ALEJANDRA", "DANIELA").replace("CANALES OPORTUS", "ORTIZ PEÑA"))
    r = _subir(estudiante_nuevo)
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "Activo"


def test_flujo_completo_rechaza_certificado_de_otra_persona(estudiante_nuevo, monkeypatch):
    monkeypatch.setattr(vc, "_leer_qr", lambda *a: "https://certificados.unab.cl/qr.php?f=1&i=2")
    monkeypatch.setattr(vc, "_descargar_pagina", lambda url: PAGINA)
    r = _subir(estudiante_nuevo)
    assert r.json()["estado"] == "Rechazado" and "RUT" in r.json()["motivo"]


# --- Vigencia semestral -------------------------------------------------------
from app import models, vigencia  # noqa: E402
from app.database import SessionLocal  # noqa: E402


@pytest.mark.parametrize("emision,vence", [
    (date(2026, 1, 1), date(2026, 6, 30)),
    (date(2026, 1, 31), date(2026, 6, 30)),
    (date(2026, 6, 30), date(2026, 6, 30)),
    (date(2026, 7, 1), date(2026, 12, 31)),
    (date(2026, 12, 31), date(2026, 12, 31)),
])
def test_fin_de_semestre(emision, vence):
    assert vigencia.fin_de_semestre(emision) == vence


def test_gracia_de_7_dias():
    v = vigencia.calcular(date(2026, 1, 20))
    assert v.vence_el == date(2026, 6, 30) and v.gracia_hasta == date(2026, 7, 7)
    assert not v.en_gracia(date(2026, 6, 30)) and not v.caducada(date(2026, 6, 30))
    assert v.en_gracia(date(2026, 7, 1)) and v.en_gracia(date(2026, 7, 7))
    assert v.caducada(date(2026, 7, 8))


def _aprobar_certificado(sesion, emision):
    """Deja al estudiante Activo con un certificado aprobado emitido en `emision`."""
    db = SessionLocal()
    try:
        db.add(models.VerificacionEstudiante(
            estudiante_id=sesion.id, archivo="x.pdf", tipo_contenido="application/pdf", tamano_bytes=1,
            estado="Aprobada", fecha_emision=emision,
        ))
        db.get(models.PerfilEstudiante, sesion.id).estado_verificacion = "Activo"
        db.commit()
    finally:
        db.close()


def _estado_en_db(usuario_id):
    db = SessionLocal()
    try:
        return db.get(models.PerfilEstudiante, usuario_id).estado_verificacion
    finally:
        db.close()


def test_vence_pasada_la_gracia_y_no_antes(estudiante_nuevo):
    _aprobar_certificado(estudiante_nuevo, date(2026, 1, 20))
    db = SessionLocal()
    try:
        assert vigencia.vencer_caducadas(db, date(2026, 7, 7)) == 0   # último día de gracia
        assert _estado_en_db(estudiante_nuevo.id) == "Activo"
        assert vigencia.vencer_caducadas(db, date(2026, 7, 8)) == 1
    finally:
        db.close()
    assert _estado_en_db(estudiante_nuevo.id) == "No verificado"


def test_aprobacion_manual_del_admin_sin_certificado_no_vence(estudiante):
    db = SessionLocal()
    try:
        assert vigencia.vencer_caducadas(db, date(2030, 1, 1)) == 0
    finally:
        db.close()
    assert _estado_en_db(estudiante.id) == "Activo"


def test_estudiante_en_gracia_conserva_acceso_y_recibe_aviso(estudiante_nuevo, monkeypatch):
    hoy = date.today()
    emision = date(hoy.year - 1, 12, 15)  # su semestre terminó hace tiempo...
    _aprobar_certificado(estudiante_nuevo, emision)
    # ...pero para esta prueba "hoy" cae dentro de la gracia
    fin = vigencia.fin_de_semestre(emision)
    from datetime import datetime
    monkeypatch.setattr("app.servicios.ahora", lambda: datetime(fin.year, fin.month, fin.day) + vigencia.timedelta(days=3))
    monkeypatch.setattr("app.vigencia.ahora", lambda: datetime(fin.year, fin.month, fin.day) + vigencia.timedelta(days=3))
    monkeypatch.setattr("app.routers.verificacion.ahora", lambda: datetime(fin.year, fin.month, fin.day) + vigencia.timedelta(days=3))
    monkeypatch.setattr("app.routers.resumen.ahora", lambda: datetime(fin.year, fin.month, fin.day) + vigencia.timedelta(days=3))
    r = estudiante_nuevo.get("/api/verificacion").json()
    assert r["estado"] == "Activo" and r["en_gracia"] is True
    assert r["vence_el"] == fin.isoformat() and "antes del" in r["mensaje"]
    assert estudiante_nuevo.get("/api/resumen").json()["notificaciones"] >= 1


def test_estudiante_vencido_pierde_acceso_en_su_siguiente_peticion(estudiante_nuevo):
    _aprobar_certificado(estudiante_nuevo, date(2020, 1, 10))
    r = estudiante_nuevo.get("/api/verificacion").json()
    assert r["estado"] == "No verificado" and r["puede_subir"] is True
