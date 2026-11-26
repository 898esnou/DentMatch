"""Requerimientos (con su tutor) y ramos del estudiante."""
from tests.conftest import REQUERIMIENTO


def test_declarar_y_listar_requerimiento(estudiante):
    r = estudiante.post("/api/requerimientos", json=REQUERIMIENTO)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["tutor"] == "Prof. Ricardo"
    assert req["estado"] == "Abierto"
    assert req["restantes"] == 2 and req["area_nombre"] == "Endodoncia"
    lista = estudiante.get("/api/requerimientos").json()
    assert [x["id"] for x in lista] == [req["id"]]


def test_tutor_es_obligatorio_y_area_se_valida(estudiante):
    sin_tutor = {k: v for k, v in REQUERIMIENTO.items() if k != "tutor"}
    assert estudiante.post("/api/requerimientos", json=sin_tutor).status_code == 422
    assert estudiante.post("/api/requerimientos", json={**REQUERIMIENTO, "area": "inventada"}).status_code == 422
    assert estudiante.post("/api/requerimientos", json={**REQUERIMIENTO, "cantidad_requerida": 0}).status_code == 422


def test_cada_estudiante_ve_solo_los_suyos(estudiante, estudiante2):
    req = estudiante.post("/api/requerimientos", json=REQUERIMIENTO).json()
    assert estudiante2.get("/api/requerimientos").json() == []
    assert estudiante2.get(f"/api/requerimientos/{req['id']}").status_code == 404
    assert estudiante2.patch(f"/api/requerimientos/{req['id']}", json={"tutor": "Otro"}).status_code == 404
    assert estudiante2.delete(f"/api/requerimientos/{req['id']}").status_code == 404


def test_avance_manual_completa_el_requerimiento(estudiante):
    req = estudiante.post("/api/requerimientos", json=REQUERIMIENTO).json()
    r = estudiante.post(f"/api/requerimientos/{req['id']}/avance", json={"cantidad": 1}).json()
    assert r["cantidad_completada"] == 1 and r["estado"] == "Abierto" and r["restantes"] == 1
    r = estudiante.post(f"/api/requerimientos/{req['id']}/avance", json={}).json()
    assert r["estado"] == "Completado" and r["restantes"] == 0
    assert estudiante.post(f"/api/requerimientos/{req['id']}/avance", json={}).status_code == 409


def test_editar_y_cancelar_requerimiento(estudiante):
    req = estudiante.post("/api/requerimientos", json=REQUERIMIENTO).json()
    r = estudiante.patch(f"/api/requerimientos/{req['id']}", json={"tutor": "Prof. Felipe"})
    assert r.json()["tutor"] == "Prof. Felipe"
    assert estudiante.patch(f"/api/requerimientos/{req['id']}", json={"tutor": None}).status_code == 422
    estudiante.post(f"/api/requerimientos/{req['id']}/avance", json={"cantidad": 2})
    assert estudiante.patch(f"/api/requerimientos/{req['id']}", json={"cantidad_requerida": 1}).status_code == 422
    assert estudiante.delete(f"/api/requerimientos/{req['id']}").status_code == 409  # ya completado

    otro = estudiante.post("/api/requerimientos", json=REQUERIMIENTO).json()
    assert estudiante.delete(f"/api/requerimientos/{otro['id']}").json()["estado"] == "Cancelado"
    assert estudiante.post(f"/api/requerimientos/{otro['id']}/avance", json={}).status_code == 409


def test_filtro_por_estado(estudiante):
    estudiante.post("/api/requerimientos", json=REQUERIMIENTO)
    assert len(estudiante.get("/api/requerimientos?estado=Abierto").json()) == 1
    assert estudiante.get("/api/requerimientos?estado=Completado").json() == []
    assert estudiante.get("/api/requerimientos?estado=Raro").status_code == 422


def test_ramos_crud_y_validacion_de_horario(estudiante, estudiante2):
    ramo = {"ramo": "Endodoncia", "area": "endodoncia", "tutor": "Prof. Ricardo", "dia_semana": "Martes",
            "hora_inicio": "14:30", "hora_fin": "16:00", "clinica": "Clínica Endodoncia I"}
    creado = estudiante.post("/api/ramos", json=ramo)
    assert creado.status_code == 201, creado.text
    rid = creado.json()["id"]
    assert estudiante.post("/api/ramos", json={**ramo, "hora_fin": "13:00"}).status_code == 422
    assert estudiante.post("/api/ramos", json={**ramo, "hora_inicio": "25:99"}).status_code == 422
    assert estudiante.put(f"/api/ramos/{rid}", json={**ramo, "lugar": "Box 8"}).json()["lugar"] == "Box 8"
    assert estudiante2.put(f"/api/ramos/{rid}", json=ramo).status_code == 404
    assert estudiante2.delete(f"/api/ramos/{rid}").status_code == 404
    assert estudiante.delete(f"/api/ramos/{rid}").status_code == 204
    assert estudiante.get("/api/ramos").json() == []
