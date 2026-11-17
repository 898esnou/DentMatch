"""
Pruebas de los problemas corregidos en la auditoría del código (noviembre 2026):
- la búsqueda semántica no muestra estudiantes baneados o en time-out,
- el correo no distingue mayúsculas (registro, duplicados y login),
- el registro valida sus campos en el backend y no deja usuarios a medias,
- las búsquedas de texto tratan % y _ como caracteres normales,
- el vencimiento semestral se revisa sin recorrer a todos los estudiantes en cada petición.
"""
from datetime import date

from app import models, vigencia
from app.database import SessionLocal
from app.utils import patron_contiene
from tests.conftest import SOLICITUD, crear_sesion
from tests.test_busqueda import crear_estudiante, falsa_busqueda  # noqa: F401  (fixture)


def _sancionar(usuario_id, estado="baneado"):
    db = SessionLocal()
    try:
        db.add(models.EstadoCuenta(usuario_id=usuario_id, estado=estado))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- búsqueda semántica
def test_la_busqueda_no_muestra_estudiantes_sancionados(paciente, falsa_busqueda):  # noqa: F811
    visible = crear_estudiante(1)
    baneado = crear_estudiante(2)
    en_time_out = crear_estudiante(3)
    _sancionar(baneado, "baneado")
    _sancionar(en_time_out, "suspendido")

    r = paciente.post("/api/busqueda", json={"texto": "necesito una limpieza dental"})
    assert r.status_code == 200, r.text
    assert [e["id"] for e in r.json()["estudiantes"]] == [visible]


# ---------------------------------------------------------------- correo sin mayúsculas
def test_el_correo_no_distingue_mayusculas(client):
    r = client.post("/api/registro", data={
        "nombre_completo": "Ana Pérez Soto", "rut": "12.345.678-5", "correo": "  Ana.Perez@Correo.CL ",
        "contrasena": "123456", "rol": "paciente",
    })
    assert r.status_code == 201, r.text
    assert r.json()["correo"] == "ana.perez@correo.cl"

    # Mismo correo escrito distinto: es la misma cuenta.
    otra = client.post("/api/registro", data={
        "nombre_completo": "Otra Persona", "rut": "11.111.111-1", "correo": "ANA.PEREZ@correo.cl",
        "contrasena": "123456", "rol": "paciente",
    })
    assert otra.status_code == 400 and "correo" in otra.json()["detail"]
    assert client.post("/api/login", json={"correo": "ANA.Perez@correo.cl", "contrasena": "123456"}).status_code == 200


def test_una_cuenta_antigua_guardada_con_mayusculas_puede_entrar(client):
    from app.auth import hash_password
    db = SessionLocal()
    db.add(models.Usuario(nombre_completo="Cuenta Antigua", rut="1-9", correo="Antigua@Test.cl",
                          contrasena_hash=hash_password("123456"), rol="paciente"))
    db.commit()
    db.close()
    assert client.post("/api/login", json={"correo": "antigua@test.cl", "contrasena": "123456"}).status_code == 200


# ---------------------------------------------------------------- validación del registro
def test_el_registro_valida_los_campos_en_el_backend(client):
    base = {"nombre_completo": "Ana Pérez Soto", "rut": "12.345.678-5", "correo": "ana@test.cl",
            "contrasena": "123456", "rol": "paciente"}
    assert client.post("/api/registro", data={**base, "contrasena": "123"}).status_code == 422
    assert client.post("/api/registro", data={**base, "contrasena": "x" * 73}).status_code == 422
    assert client.post("/api/registro", data={**base, "correo": "no-es-un-correo"}).status_code == 400
    assert client.post("/api/registro", data={**base, "nombre_completo": "x" * 151}).status_code == 422
    assert client.post("/api/registro", data={**base, "tipo_documento": "otro"}).status_code == 400
    # Nada de lo anterior dejó un usuario creado.
    db = SessionLocal()
    try:
        assert db.query(models.Usuario).count() == 0
    finally:
        db.close()


def test_el_registro_crea_usuario_y_perfil_juntos(client):
    r = client.post("/api/registro", data={
        "nombre_completo": "  Matías   Rojas  ", "rut": "12.345.678-5", "correo": "m@test.cl",
        "contrasena": "123456", "rol": "estudiante", "universidad": "U. de Chile", "ano_carrera": 5,
    })
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        usuario = db.get(models.Usuario, r.json()["id"])
        assert usuario.nombre_completo == "Matías Rojas"
        assert usuario.perfil_estudiante.estado_verificacion == "No verificado"
    finally:
        db.close()


# ---------------------------------------------------------------- búsquedas de texto
def test_patron_contiene_escapa_los_comodines():
    assert patron_contiene(" 100% ") == "%100\\%%"
    assert patron_contiene("a_b") == "%a\\_b%"


def test_buscar_un_comodin_no_devuelve_todo(paciente, estudiante):
    paciente.post("/api/solicitudes", json=SOLICITUD)
    assert len(estudiante.get("/api/casos").json()) == 1
    assert estudiante.get("/api/casos", params={"q": "%"}).json() == []
    assert estudiante.get("/api/casos", params={"comuna": "_"}).json() == []


# ---------------------------------------------------------------- vencimiento semestral
def test_vencer_si_caducada_revisa_solo_a_esa_persona(client):
    otro = crear_sesion(client, "estudiante", "otro@test.cl", "22.222.222-2", "Otro Estudiante")
    yo = crear_sesion(client, "estudiante", "yo@test.cl", "11.111.111-1", "Yo Estudiante")
    db = SessionLocal()
    try:
        for sesion in (otro, yo):
            db.add(models.VerificacionEstudiante(
                estudiante_id=sesion.id, archivo="x.pdf", tipo_contenido="application/pdf", tamano_bytes=1,
                estado="Aprobada", fecha_emision=date(2020, 1, 10),
            ))
        db.commit()
        assert vigencia.vencer_si_caducada(db, db.get(models.Usuario, yo.id)) is True
        assert db.get(models.PerfilEstudiante, yo.id).estado_verificacion == "No verificado"
        assert db.get(models.PerfilEstudiante, otro.id).estado_verificacion == "Activo"
    finally:
        db.close()
