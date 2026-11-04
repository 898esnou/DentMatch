"""
Búsqueda semántica: catálogo, puntaje de coincidencia, aviso de urgencia y opiniones.

Ninguna prueba llama a la API de Gemini (no gastan cuota ni necesitan clave): la función
`buscar` del router se reemplaza por una falsa que devuelve resultados de ejemplo.
"""
from collections import defaultdict, deque

import numpy as np
import pytest
from fastapi import HTTPException

from app import models
from app.busqueda_semantica import (
    BuscadorNoDisponible,
    cargar_catalogo,
    frase_de_la_fila,
    mejor_fila_por_procedimiento,
    nivel_coincidencia,
    ordenar_por_procedimiento,
    validar_catalogo,
)
from app.auth import hash_password
from app.database import SessionLocal
from app.matching import (
    calcular_puntaje,
    interpretar_disponibilidad,
    motivos_de_coincidencia,
    normalizar,
    paginar,
    puntaje_disponibilidad,
    puntaje_procedimiento,
    puntaje_ubicacion,
)
from app.routers import busqueda as router_busqueda
from app.urgencia import MENSAJE_URGENCIA, detectar_urgencia
from tests.conftest import Sesion


# ------------------------------------------------------------------ ayudas
@pytest.fixture(autouse=True)
def limpiar_limitadores():
    """El límite por minuto vive en memoria: se reinicia para que las pruebas no se afecten."""
    router_busqueda._historial.clear()
    router_busqueda._historial_opiniones.clear()


def una_coincidencia(id="limpieza", nombre="Profilaxis dental", area="prevencion",
                     puntaje=0.9, nivel="alta", frase="Limpieza dental"):
    return {"id": id, "nombre": nombre, "area": area, "puntaje": puntaje, "coincidencia": nivel, "frase": frase}


@pytest.fixture()
def falsa_busqueda(monkeypatch):
    """Reemplaza buscar() del router. Se controla con el diccionario que devuelve."""
    estado = {"resultado": [una_coincidencia()], "error": None, "consultas": []}

    def falsa(consulta, top_k=3, umbral=0.5):
        estado["consultas"].append(consulta)
        if estado["error"]:
            raise estado["error"]
        return estado["resultado"]

    monkeypatch.setattr(router_busqueda, "buscar", falsa)
    return estado


def crear_estudiante(i, area="prevencion", comuna="Recoleta", disponibilidad=None,
                     estado="Activo", requerimiento="Abierto"):
    """Crea directo en la base un estudiante con un requerimiento (atajo para no registrar a cada uno)."""
    db = SessionLocal()
    try:
        usuario = models.Usuario(
            nombre_completo=f"Estudiante{i} Apellido", rut=f"EXT-9{i:06d}", correo=f"est{i}@test.cl",
            contrasena_hash="no-se-usa", rol="estudiante",
        )
        db.add(usuario)
        db.flush()
        db.add(models.PerfilEstudiante(
            usuario_id=usuario.id, universidad="Universidad de Chile", ano_carrera=5,
            comuna_atencion=comuna, disponibilidad=disponibilidad, estado_verificacion=estado,
        ))
        db.add(models.Requerimiento(
            estudiante_id=usuario.id, tratamiento="Limpieza dental", area=area, tutor="Prof. Ricardo",
            cantidad_requerida=2, cantidad_completada=0, estado=requerimiento,
        ))
        db.commit()
        return usuario.id
    finally:
        db.close()


def crear_admin(client):
    db = SessionLocal()
    db.add(models.Usuario(nombre_completo="Admin Prueba", rut="1-9", correo="admin@test.cl",
                          contrasena_hash=hash_password("123456"), rol="admin"))
    db.commit()
    db.close()
    token = client.post("/api/login", json={"correo": "admin@test.cl", "contrasena": "123456"}).json()["access_token"]
    return Sesion(client, 0, {"Authorization": f"Bearer {token}"}, "Admin")


# ------------------------------------------------------------------ catálogo
def test_el_catalogo_real_es_valido():
    catalogo, _ = cargar_catalogo()
    validar_catalogo(catalogo)  # ids únicos, áreas válidas y frases presentes
    vistas = set()
    for procedimiento in catalogo:
        assert procedimiento["nombre_profesional"].strip()
        assert len(procedimiento["frases"]) >= 3, f"{procedimiento['id']} tiene muy pocas frases"
        for frase in procedimiento["frases"]:
            assert frase.strip() == frase and frase, f"Frase vacía o con espacios sobrantes: {frase!r}"
            clave = normalizar(frase)
            assert clave not in vistas, f"Frase repetida en el catálogo: {frase!r}"
            vistas.add(clave)


def test_validar_catalogo_rechaza_errores():
    bueno = {"id": "a", "nombre_profesional": "A", "area": "prevencion", "frases": ["x"]}
    validar_catalogo([bueno])
    with pytest.raises(ValueError):
        validar_catalogo([bueno, dict(bueno)])                       # id repetido
    with pytest.raises(ValueError):
        validar_catalogo([{**bueno, "area": "inventada"}])           # área que no existe
    with pytest.raises(ValueError):
        validar_catalogo([{**bueno, "frases": []}])                  # sin frases


# ------------------------------------------------------------------ puntajes de similitud
def test_mejor_fila_y_frase_que_coincidio():
    ids = ["a", "a", "b"]
    datos = {"a": {"frases": ["primera", "segunda"]}, "b": {"frases": ["otra"]}}
    mejor = mejor_fila_por_procedimiento(np.array([0.2, 0.9, 0.5]), ids)
    assert mejor == {"a": (pytest.approx(0.9), 1), "b": (pytest.approx(0.5), 2)}
    assert frase_de_la_fila(1, ids, datos) == "segunda"
    assert frase_de_la_fila(2, ids, datos) == "otra"


def test_ordenar_por_procedimiento_usa_la_mejor_frase_y_el_umbral():
    ids = ["a", "a", "b", "c"]
    puntajes = np.array([0.6, 0.9, 0.8, 0.3])
    assert ordenar_por_procedimiento(puntajes, ids, top_k=3, umbral=0.0) == [("a", 0.9), ("b", 0.8), ("c", 0.3)]
    assert ordenar_por_procedimiento(puntajes, ids, top_k=3, umbral=0.5) == [("a", 0.9), ("b", 0.8)]
    assert ordenar_por_procedimiento(puntajes, ids, top_k=1, umbral=0.5) == [("a", 0.9)]
    assert ordenar_por_procedimiento(puntajes, ids, top_k=3, umbral=0.95) == []


def test_niveles_de_coincidencia():
    assert nivel_coincidencia(0.95) == "alta"
    assert nivel_coincidencia(0.78) == "media"
    assert nivel_coincidencia(0.5) == "baja"


# ------------------------------------------------------------------ urgencia
@pytest.mark.parametrize("texto", [
    "se me hinchó la cara y tengo fiebre",
    "tengo la mejilla inflamada desde ayer",
    "me salió pus en la encía",
    "no puedo tragar ni abrir la boca",
    "me pegué un golpe en la boca y se me soltó un diente",
    "tengo un dolor insoportable en una muela",
    "no para de sangrar después de sacarme la muela",
])
def test_detecta_senales_de_urgencia(texto):
    assert detectar_urgencia(texto)


@pytest.mark.parametrize("texto", [
    "quiero una limpieza dental barata",
    "me sangran las encías y tengo sarro",
    "se me quebró un diente al comer",
    "me arde el diente cuando tomo agua fría",
    "tengo la muela del juicio mala",
    "hace mucho que no me reviso la boca",
    "tengo las encías inflamadas y rojas",
])
def test_no_marca_urgencia_en_consultas_comunes(texto):
    assert not detectar_urgencia(texto)


# ------------------------------------------------------------------ puntaje de coincidencia
def test_puntaje_de_ubicacion():
    assert puntaje_ubicacion("Recoleta", " recoleta ") == 1.0
    assert puntaje_ubicacion("Recoleta", "Ñuñoa") == 0.0
    assert puntaje_ubicacion("Recoleta", "Por definir") is None  # el estudiante aún no la completó
    assert puntaje_ubicacion(None, "Recoleta") is None
    assert puntaje_ubicacion("Ñuñoa", "nunoa") == 1.0  # ignora tildes y mayúsculas


def test_interpretar_disponibilidad():
    dias, turnos = interpretar_disponibilidad("Lunes a viernes por la tarde")
    assert dias == {"lunes", "martes", "miercoles", "jueves", "viernes"} and turnos == {"tarde"}
    assert interpretar_disponibilidad("martes y jueves por la mañana") == ({"martes", "jueves"}, {"manana"})
    assert interpretar_disponibilidad("fines de semana")[0] == {"sabado", "domingo"}
    assert interpretar_disponibilidad("de viernes a lunes")[0] == {"viernes", "sabado", "domingo", "lunes"}
    dias, turnos = interpretar_disponibilidad("cualquier día")
    assert len(dias) == 7 and len(turnos) == 3
    assert interpretar_disponibilidad("") == (set(), set())
    assert interpretar_disponibilidad(None) == (set(), set())


def test_puntaje_de_disponibilidad():
    # 1 de los 5 días del paciente coincide (0.2) y el turno coincide (1.0): promedio 0.6
    assert puntaje_disponibilidad("lunes a viernes por la tarde", "martes por la tarde") == pytest.approx(0.6)
    assert puntaje_disponibilidad("lunes", "martes") == 0.0
    assert puntaje_disponibilidad("martes por la tarde", "martes por la tarde") == 1.0
    assert puntaje_disponibilidad(None, "martes") is None       # sin dato no se compara
    assert puntaje_disponibilidad("lunes", "") is None


def test_puntaje_de_procedimiento_se_lleva_a_cero_uno():
    assert puntaje_procedimiento(0.75, 0.75) == 0.0
    assert puntaje_procedimiento(0.7, 0.75) == 0.0
    assert puntaje_procedimiento(0.875, 0.75) == pytest.approx(0.5)
    assert puntaje_procedimiento(1.0, 0.75) == 1.0


def test_puntaje_final_y_orden():
    assert calcular_puntaje(1.0, 1.0, 1.0) == 100
    assert calcular_puntaje(0.0, 0.0, 0.0) == 0
    assert calcular_puntaje(1.0, None, None) == 75            # lo que falta cuenta como neutro (0.5)
    coincide = calcular_puntaje(0.6, 1.0, 1.0)
    desconocido = calcular_puntaje(0.6, None, None)
    distinto = calcular_puntaje(0.6, 0.0, 0.0)
    assert coincide > desconocido > distinto


def test_motivos_de_coincidencia():
    assert motivos_de_coincidencia("Endodoncia", 1.0, 1.0) == [
        "Necesita pacientes de Endodoncia", "Atiende en tu comuna", "Su disponibilidad coincide con la tuya",
    ]
    assert motivos_de_coincidencia("Endodoncia", 0.0, None) == ["Necesita pacientes de Endodoncia"]


def test_paginar():
    elementos = list(range(25))
    pagina, total = paginar(elementos, 1)
    assert pagina == list(range(10)) and total == 3
    assert paginar(elementos, 3)[0] == [20, 21, 22, 23, 24]
    assert paginar(elementos, 99)[0] == [20, 21, 22, 23, 24]   # una página inexistente cae en la última
    assert paginar([], 1) == ([], 1)


# ------------------------------------------------------------------ endpoint /api/busqueda
def test_la_consulta_exige_ser_paciente(client, estudiante, falsa_busqueda):
    assert client.post("/api/busqueda", json={"texto": "quiero una limpieza"}).status_code == 401
    assert estudiante.post("/api/busqueda", json={"texto": "quiero una limpieza"}).status_code == 403


def test_texto_demasiado_corto(paciente, falsa_busqueda):
    assert paciente.post("/api/busqueda", json={"texto": "ab"}).status_code == 422
    assert falsa_busqueda["consultas"] == []  # ni siquiera llega al buscador


def test_sin_coincidencia_explica_que_hacer(paciente, falsa_busqueda):
    falsa_busqueda["resultado"] = []
    r = paciente.post("/api/busqueda", json={"texto": "quiero comprar una pizza"}).json()
    assert r["procedimientos"] == [] and r["estudiantes"] == []
    assert r["mensaje"] == router_busqueda.MENSAJE_SIN_COINCIDENCIA
    assert r["aviso_urgencia"] is None


def test_coincidencia_alta_muestra_la_frase_y_estudiantes(paciente, falsa_busqueda):
    crear_estudiante(1)
    r = paciente.post("/api/busqueda", json={"texto": "quiero limpiarme los dientes"}).json()
    assert r["procedimientos"][0]["coincide_con"] == "Limpieza dental"
    assert r["mensaje"] is None                                  # coincidencia alta: sin mensaje de duda
    assert r["area_sugerida"] == "prevencion"
    assert len(r["estudiantes"]) == 1
    e = r["estudiantes"][0]
    assert 0 <= e["puntaje"] <= 100 and "Necesita pacientes de Limpieza y Prevención" in e["motivos"]
    assert "correo" not in e and "rut" not in e                  # no se expone nada sensible


def test_coincidencia_media_pide_hablar_con_el_estudiante(paciente, falsa_busqueda):
    falsa_busqueda["resultado"] = [una_coincidencia(puntaje=0.78, nivel="media")]
    r = paciente.post("/api/busqueda", json={"texto": "me duele algo en la boca"}).json()
    assert r["mensaje"] == router_busqueda.MENSAJE_COINCIDENCIA_MEDIA


def test_solo_aparecen_estudiantes_verificados_con_cupo_en_el_area(paciente, falsa_busqueda):
    bueno = crear_estudiante(1)
    crear_estudiante(2, estado="No verificado")
    crear_estudiante(3, estado="En Verificación")
    crear_estudiante(4, requerimiento="Cancelado")
    crear_estudiante(5, area="cirugia")
    r = paciente.post("/api/busqueda", json={"texto": "quiero limpiarme los dientes"}).json()
    assert [e["id"] for e in r["estudiantes"]] == [bueno]


def test_los_estudiantes_se_ordenan_por_puntaje(paciente, falsa_busqueda):
    paciente.put("/api/perfil/paciente", json={"comuna": "Recoleta", "disponibilidad": "martes por la tarde"})
    lejos = crear_estudiante(1, comuna="Ñuñoa", disponibilidad="lunes por la mañana")
    ideal = crear_estudiante(2, comuna="Recoleta", disponibilidad="martes por la tarde")
    sin_datos = crear_estudiante(3, comuna="Por definir", disponibilidad=None)
    r = paciente.post("/api/busqueda", json={"texto": "quiero limpiarme los dientes"}).json()
    assert [e["id"] for e in r["estudiantes"]] == [ideal, sin_datos, lejos]
    assert [e["puntaje"] for e in r["estudiantes"]] == [80, 55, 30]
    assert "Atiende en tu comuna" in r["estudiantes"][0]["motivos"]


def test_los_resultados_se_paginan_de_a_diez(paciente, falsa_busqueda):
    ids = [crear_estudiante(i) for i in range(1, 13)]
    pagina1 = paciente.post("/api/busqueda", json={"texto": "quiero limpiarme los dientes"}).json()
    pagina2 = paciente.post("/api/busqueda", json={"texto": "quiero limpiarme los dientes", "pagina": 2}).json()
    assert (pagina1["pagina"], pagina1["paginas"], pagina1["total_estudiantes"]) == (1, 2, 12)
    assert len(pagina1["estudiantes"]) == 10 and len(pagina2["estudiantes"]) == 2
    vistos = [e["id"] for e in pagina1["estudiantes"]] + [e["id"] for e in pagina2["estudiantes"]]
    assert sorted(vistos) == sorted(ids)  # ninguno repetido ni faltante


def test_aviso_de_urgencia(paciente, falsa_busqueda):
    r = paciente.post("/api/busqueda", json={"texto": "se me hinchó la cara y tengo fiebre"}).json()
    assert r["aviso_urgencia"] == MENSAJE_URGENCIA
    r = paciente.post("/api/busqueda", json={"texto": "quiero una limpieza dental"}).json()
    assert r["aviso_urgencia"] is None


def test_si_falla_la_api_responde_503_sin_filtrar_el_texto(paciente, falsa_busqueda, caplog):
    falsa_busqueda["error"] = BuscadorNoDisponible("cuota agotada")
    r = paciente.post("/api/busqueda", json={"texto": "mal aliento y dientes amarillos"})
    assert r.status_code == 503
    assert "mal aliento" not in caplog.text  # el texto del paciente nunca se escribe en los logs


def test_limite_de_consultas_por_minuto(paciente, falsa_busqueda):
    for _ in range(router_busqueda.CONSULTAS_POR_VENTANA):
        assert paciente.post("/api/busqueda", json={"texto": "quiero una limpieza"}).status_code == 200
    assert paciente.post("/api/busqueda", json={"texto": "quiero una limpieza"}).status_code == 429


def test_limite_con_reloj_simulado():
    historial = defaultdict(deque)
    for _ in range(3):
        router_busqueda.verificar_limite(7, ahora=100.0, historial=historial, maximo=3)
    with pytest.raises(HTTPException):
        router_busqueda.verificar_limite(7, ahora=101.0, historial=historial, maximo=3)
    router_busqueda.verificar_limite(7, ahora=100.0 + router_busqueda.VENTANA_SEGUNDOS + 1, historial=historial, maximo=3)


# ------------------------------------------------------------------ opiniones ("¿Te sirvió?")
def test_la_opinion_se_guarda_sin_texto_ni_usuario(paciente):
    r = paciente.post("/api/busqueda/retroalimentacion",
                      json={"util": True, "procedimiento_id": "limpieza", "coincidencia": "alta"})
    assert r.status_code == 201
    db = SessionLocal()
    try:
        filas = db.query(models.RetroalimentacionBusqueda).all()
        assert len(filas) == 1
        assert (filas[0].procedimiento_id, filas[0].coincidencia, filas[0].util) == ("limpieza", "alta", True)
        assert {c.name for c in models.RetroalimentacionBusqueda.__table__.columns} == {
            "id", "procedimiento_id", "coincidencia", "util", "fecha"}  # nada que identifique a la persona
    finally:
        db.close()


def test_opinion_con_procedimiento_desconocido_o_rol_incorrecto(paciente, estudiante):
    assert paciente.post("/api/busqueda/retroalimentacion",
                         json={"util": True, "procedimiento_id": "inventado"}).status_code == 422
    assert paciente.post("/api/busqueda/retroalimentacion",
                         json={"util": True, "coincidencia": "enorme"}).status_code == 422
    assert estudiante.post("/api/busqueda/retroalimentacion", json={"util": True}).status_code == 403


def test_estadisticas_de_opiniones_solo_para_el_admin(client, paciente, estudiante):
    for util in (True, True, False):
        paciente.post("/api/busqueda/retroalimentacion", json={"util": util, "procedimiento_id": "limpieza"})
    paciente.post("/api/busqueda/retroalimentacion", json={"util": False})  # una consulta sin coincidencia

    assert paciente.get("/api/busqueda/estadisticas").status_code == 403
    assert estudiante.get("/api/busqueda/estadisticas").status_code == 403

    admin = crear_admin(client)
    filas = {f["procedimiento_id"]: f for f in admin.get("/api/busqueda/estadisticas").json()}
    assert filas["limpieza"]["total"] == 3 and filas["limpieza"]["utiles"] == 2
    assert filas["limpieza"]["no_utiles"] == 1 and filas["limpieza"]["porcentaje_utiles"] == 67
    assert filas["limpieza"]["nombre"] == "Profilaxis dental"
    assert filas[None]["total"] == 1 and filas[None]["nombre"] == "Sin coincidencia"


# ------------------------------------------------------------------ caché del índice (despliegue)
from app import busqueda_semantica as bs  # noqa: E402


def _guardar_cache(ruta, hash_cache):
    catalogo, _ = cargar_catalogo()
    ids = [p["id"] for p in catalogo for _ in p["frases"]]
    np.savez(ruta, vectores=np.ones((len(ids), 4), dtype=np.float32), ids=np.array(ids), hash=hash_cache)
    return ids


def _api_prohibida(*args, **kwargs):
    raise AssertionError("Esta prueba no debe llamar a la API de embeddings")


def test_el_indice_usa_el_cache_sin_llamar_a_la_api(monkeypatch, tmp_path):
    _, hash_actual = cargar_catalogo()
    ids_esperados = _guardar_cache(tmp_path / "cache.npz", hash_actual)
    monkeypatch.setattr(bs, "RUTA_CACHE", tmp_path / "cache.npz")
    monkeypatch.setattr(bs, "embeber", _api_prohibida)
    vectores, ids, datos = bs.construir_indice()
    assert ids == ids_esperados and vectores.shape[0] == len(ids_esperados)


def test_en_vercel_sin_cache_falla_con_un_mensaje_claro(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(bs, "RUTA_CACHE", tmp_path / "no_existe.npz")
    monkeypatch.setattr(bs, "embeber", _api_prohibida)  # no debe intentar construirlo
    with pytest.raises(BuscadorNoDisponible, match="construir_cache"):
        bs.construir_indice()


def test_en_vercel_un_cache_desactualizado_tampoco_se_reconstruye(monkeypatch, tmp_path):
    _guardar_cache(tmp_path / "viejo.npz", "hash-de-otra-version-del-json")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(bs, "RUTA_CACHE", tmp_path / "viejo.npz")
    monkeypatch.setattr(bs, "embeber", _api_prohibida)
    with pytest.raises(BuscadorNoDisponible):
        bs.construir_indice()


def test_un_disco_de_solo_lectura_no_rompe_la_busqueda(monkeypatch, tmp_path):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(bs, "RUTA_CACHE", tmp_path / "no_existe.npz")
    total = sum(len(p["frases"]) for p in cargar_catalogo()[0])
    monkeypatch.setattr(bs, "embeber", lambda frases, tipo: np.ones((len(frases), 4), dtype=np.float32))

    def sin_permiso(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(bs.np, "savez", sin_permiso)
    vectores, ids, _ = bs.construir_indice()  # no lanza: sigue con el índice en memoria
    assert vectores.shape[0] == total == len(ids)
