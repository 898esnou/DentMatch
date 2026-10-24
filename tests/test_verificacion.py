"""Documento de identidad (RUT chileno o extranjero) y verificación del estudiante."""
import pytest

from app.documentos import (
    normalizar_documento, normalizar_documento_extranjero, normalizar_rut, variantes_guardadas,
)
from tests.conftest import (
    PDF_VALIDO, PNG_VALIDO, REQUERIMIENTO, SOLICITUD, Sesion, crear_sesion, marcar_estado_verificacion,
)
from tests.test_admin import _crear_admin


# ---------- documento: funciones puras ----------
@pytest.mark.parametrize("texto", ["12.345.678-5", "12345678-5", "123456785", " 12345678-5 "])
def test_rut_valido_se_normaliza(texto):
    assert normalizar_rut(texto) == "12345678-5"


def test_rut_con_k_y_digito_cero():
    assert normalizar_rut("1.000.005-k") == "1000005-K"   # dígito verificador K
    assert normalizar_rut("1.000.013-0") == "1000013-0"   # dígito verificador 0


@pytest.mark.parametrize("texto", ["12345678-9", "12345678-K", "1234-5", "abcdefgh-1", "", "12.345.678-55"])
def test_rut_invalido(texto):
    with pytest.raises(ValueError):
        normalizar_rut(texto)


def test_documento_extranjero():
    assert normalizar_documento("extranjero", "ab-123 456") == "EXT-AB123456"
    for malo in ("1234", "A" * 17, "AB@12345"):
        with pytest.raises(ValueError):
            normalizar_documento_extranjero(malo)
    with pytest.raises(ValueError):
        normalizar_documento("otro", "12345678-5")


def test_variantes_para_detectar_duplicados():
    assert variantes_guardadas("12345678-5") == ["12345678-5", "12.345.678-5"]
    assert variantes_guardadas("EXT-AB123456") == ["EXT-AB123456"]


# ---------- registro ----------
def _registro(client, **extra):
    datos = {"nombre_completo": "Persona Prueba", "rut": "12345678-5", "correo": "p@test.cl",
             "contrasena": "123456", "rol": "paciente"}
    datos.update(extra)
    return client.post("/api/registro", data=datos)


def test_registro_rechaza_rut_invalido(client):
    r = _registro(client, rut="12345678-9")
    assert r.status_code == 400 and "dígito verificador" in r.json()["detail"]


def test_registro_guarda_rut_normalizado_y_evita_duplicados(client):
    assert _registro(client, rut="12.345.678-5").status_code == 201
    # el mismo RUT escrito de otra forma, con otro correo, es duplicado
    otro = _registro(client, rut="123456785", correo="otro@test.cl")
    assert otro.status_code == 400 and "ya está registrado" in otro.json()["detail"]


def test_registro_detecta_duplicado_guardado_con_puntos(client):
    """Los registros antiguos pueden tener puntos: no debe poder repetirse."""
    crear_sesion(client, "paciente", "viejo@test.cl", "33.333.333-3", "Paciente Antiguo")
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    db.query(models.Usuario).filter_by(correo="viejo@test.cl").one().rut = "33.333.333-3"
    db.commit(); db.close()
    assert _registro(client, rut="33333333-3", correo="nuevo2@test.cl").status_code == 400


def test_registro_documento_extranjero(client):
    r = _registro(client, rut="ab-123456", tipo_documento="extranjero")
    assert r.status_code == 201
    assert _registro(client, rut="AB123456", tipo_documento="extranjero", correo="e2@test.cl").status_code == 400
    assert _registro(client, rut="1234", tipo_documento="extranjero", correo="e3@test.cl").status_code == 400
    assert _registro(client, rut="12345678-5", tipo_documento="raro", correo="e4@test.cl").status_code == 400


# ---------- estudiante nuevo ----------
def test_estudiante_nace_no_verificado(estudiante_nuevo):
    estado = estudiante_nuevo.get("/api/verificacion").json()
    assert estado["estado"] == "No verificado" and estado["puede_subir"] is True
    assert estado["certificado_subido"] is False
    assert estudiante_nuevo.get("/api/perfil").json()["estudiante"]["estado_verificacion"] == "No verificado"


def test_sin_verificar_puede_ver_casos_pero_no_actuar(estudiante_nuevo, paciente):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    assert len(estudiante_nuevo.get("/api/casos").json()) == 1          # ver, sí
    assert estudiante_nuevo.get(f"/api/casos/{sol['id']}").status_code == 200

    for r in (
        estudiante_nuevo.post("/api/postulaciones", json={"solicitud_id": sol["id"]}),
        estudiante_nuevo.post("/api/requerimientos", json=REQUERIMIENTO),
        estudiante_nuevo.post("/api/citas", json={"postulacion_id": 1, "fecha_hora": "2099-01-01T10:00:00"}),
        estudiante_nuevo.post("/api/postulaciones/1/responder", json={"accion": "aceptar"}),
        estudiante_nuevo.post("/api/postulaciones/1/completar"),
    ):
        assert r.status_code == 403, r.text
        assert "verificar tu perfil" in r.json()["detail"]
    # lo propio de su perfil sí puede editarlo
    assert estudiante_nuevo.put("/api/perfil/estudiante", json={"comuna_atencion": "Recoleta"}).status_code == 200
    assert estudiante_nuevo.post("/api/ramos", json={"ramo": "Endodoncia I"}).status_code == 201


def test_el_paciente_no_ve_ni_solicita_estudiantes_sin_verificar(estudiante_nuevo, paciente):
    assert paciente.get("/api/estudiantes").json() == []
    assert paciente.get(f"/api/estudiantes/{estudiante_nuevo.id}").status_code == 404
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    r = paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"], "estudiante_id": estudiante_nuevo.id})
    assert r.status_code == 409


def test_los_pacientes_no_pasan_por_la_verificacion(paciente):
    assert paciente.post("/api/solicitudes", json=SOLICITUD).status_code == 201
    assert paciente.get("/api/verificacion").status_code == 403  # es solo de estudiantes


# ---------- subir certificado ----------
def _subir(sesion, contenido=PDF_VALIDO, nombre="certificado.pdf", tipo="application/pdf"):
    return sesion.client.post(
        "/api/verificacion/certificado", headers=sesion.headers, files={"archivo": (nombre, contenido, tipo)}
    )


def test_subir_certificado_pasa_a_en_verificacion(estudiante_nuevo):
    r = _subir(estudiante_nuevo)
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "En Verificación" and r.json()["certificado_subido"] is True
    assert r.json()["puede_subir"] is False
    assert estudiante_nuevo.get("/api/resumen").json()["estado_verificacion"] == "En Verificación"
    # mientras se revisa no se puede mandar otro
    assert _subir(estudiante_nuevo).status_code == 409


def test_acepta_pdf_png_y_jpg(client):
    for i, (contenido, nombre) in enumerate([(PDF_VALIDO, "a.pdf"), (PNG_VALIDO, "a.png"), (b"\xff\xd8\xff\xe0" + b"0" * 20, "a.jpg")]):
        est = crear_sesion(client, "estudiante", f"e{i}@test.cl", ["11.111.111-1", "22.222.222-2", "33.333.333-3"][i],
                           "Estudiante Prueba", verificado=False)
        assert _subir(est, contenido, nombre).status_code == 201


def test_rechaza_archivos_invalidos(estudiante_nuevo):
    assert _subir(estudiante_nuevo, b"", "vacio.pdf").status_code == 422
    # un ejecutable disfrazado de PDF: se mira el contenido, no el nombre
    r = _subir(estudiante_nuevo, b"MZ\x90\x00" + b"0" * 50, "certificado.pdf", "application/pdf")
    assert r.status_code == 422 and "PDF, JPG o PNG" in r.json()["detail"]
    r = _subir(estudiante_nuevo, PDF_VALIDO + b"0" * (5 * 1024 * 1024), "grande.pdf")
    assert r.status_code == 413
    assert estudiante_nuevo.get("/api/verificacion").json()["estado"] == "No verificado"  # nada cambió


def test_pacientes_no_pueden_subir_certificado(paciente):
    assert _subir(paciente).status_code == 403


# ---------- decisión del admin ----------
def test_rechazo_con_motivo_y_nueva_subida(client, estudiante_nuevo):
    admin = _crear_admin(client)
    _subir(estudiante_nuevo)
    url = f"/api/admin/estudiantes/{estudiante_nuevo.id}/verificacion"

    # rechazar exige motivo (el estudiante debe saber qué corregir)
    assert admin.patch(url, json={"estado": "Rechazado"}).status_code == 422
    r = admin.patch(url, json={"estado": "Rechazado", "motivo": "El certificado está vencido"})
    assert r.status_code == 200

    estado = estudiante_nuevo.get("/api/verificacion").json()
    assert estado["estado"] == "Rechazado" and estado["motivo"] == "El certificado está vencido"
    assert estado["puede_subir"] is True
    assert estudiante_nuevo.get("/api/resumen").json()["notificaciones"] == 1  # la campana avisa

    # vuelve a subir: pasa de nuevo a revisión y el motivo viejo ya no se muestra
    assert _subir(estudiante_nuevo).json()["estado"] == "En Verificación"
    assert estudiante_nuevo.get("/api/verificacion").json()["motivo"] is None

    # el admin aprueba: queda activo y ya puede actuar
    assert admin.patch(url, json={"estado": "Activo"}).status_code == 200
    assert estudiante_nuevo.get("/api/verificacion").json()["estado"] == "Activo"
    assert estudiante_nuevo.get("/api/requerimientos").status_code == 200
    assert estudiante_nuevo.post("/api/requerimientos", json=REQUERIMIENTO).status_code == 201


def test_renovar_no_quita_el_acceso(estudiante):
    """Un estudiante ya verificado que sube un certificado nuevo sigue 'Activo' mientras se revisa."""
    assert _subir(estudiante).json()["estado"] == "Activo"
    assert estudiante.post("/api/requerimientos", json=REQUERIMIENTO).status_code == 201


def test_solo_el_admin_descarga_el_certificado(client, estudiante_nuevo, paciente):
    admin = _crear_admin(client)
    _subir(estudiante_nuevo)
    url = f"/api/admin/estudiantes/{estudiante_nuevo.id}/certificado"
    r = admin.get(url)
    assert r.status_code == 200 and r.content == PDF_VALIDO and r.headers["content-type"] == "application/pdf"
    assert estudiante_nuevo.get(url).status_code == 403
    assert paciente.get(url).status_code == 403
    assert admin.get(f"/api/admin/estudiantes/{paciente.id}/certificado").status_code == 404


def test_el_certificado_nunca_se_expone_al_paciente(estudiante_nuevo, paciente):
    _subir(estudiante_nuevo)
    marcar_estado_verificacion(estudiante_nuevo.id, "Activo")
    texto = paciente.get("/api/estudiantes").text
    assert "certificado" not in texto.lower() and "estudiante_" not in texto


@pytest.mark.parametrize("cuerpo", ["50000000", "76123456", "99999999"])
def test_rut_de_empresa_se_rechaza(cuerpo):
    from app.documentos import _calcular_dv
    with pytest.raises(ValueError, match="empresa"):
        normalizar_rut(f"{cuerpo}-{_calcular_dv(cuerpo)}")


def test_rut_de_persona_justo_bajo_el_limite_es_valido():
    from app.documentos import _calcular_dv
    assert normalizar_rut(f"49999999-{_calcular_dv('49999999')}").startswith("49999999")
