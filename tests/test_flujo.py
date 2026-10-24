"""Solicitudes, casos, postulaciones en ambos sentidos, citas y resumen."""
from datetime import datetime, timedelta

from tests.conftest import REQUERIMIENTO, SOLICITUD

FUTURO = (datetime.now() + timedelta(days=3)).replace(microsecond=0).isoformat()


def test_paciente_publica_y_el_estudiante_la_ve_como_caso(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD)
    assert sol.status_code == 201, sol.text
    assert sol.json()["estado"] == "Abierta" and sol.json()["urgente"] is True
    casos = estudiante.get("/api/casos").json()
    assert len(casos) == 1 and casos[0]["id"] == sol.json()["id"]
    assert casos[0]["mi_postulacion_estado"] is None


def test_la_comuna_se_toma_del_perfil_si_no_se_envia(paciente):
    paciente.put("/api/perfil/paciente", json={"comuna": "Recoleta"})
    sin_comuna = {k: v for k, v in SOLICITUD.items() if k != "comuna"}
    assert paciente.post("/api/solicitudes", json=sin_comuna).json()["comuna"] == "Recoleta"


def test_validaciones_de_solicitud(paciente):
    assert paciente.post("/api/solicitudes", json={**SOLICITUD, "descripcion": "corta"}).status_code == 422
    assert paciente.post("/api/solicitudes", json={**SOLICITUD, "area": "x"}).status_code == 422


def test_filtros_de_casos(paciente, estudiante):
    paciente.post("/api/solicitudes", json=SOLICITUD)
    paciente.post("/api/solicitudes", json={**SOLICITUD, "titulo": "Limpieza anual", "area": "prevencion",
                                            "urgente": False, "comuna": "Ñuñoa"})
    assert len(estudiante.get("/api/casos").json()) == 2
    assert estudiante.get("/api/casos").json()[0]["urgente"] is True  # urgentes primero
    assert len(estudiante.get("/api/casos?area=prevencion").json()) == 1
    assert len(estudiante.get("/api/casos?urgente=true").json()) == 1
    assert len(estudiante.get("/api/casos?comuna=uñoa").json()) == 1
    assert len(estudiante.get("/api/casos?q=limpieza").json()) == 1
    assert estudiante.get("/api/casos?area=zzz").status_code == 422


def test_paciente_ve_solo_sus_solicitudes(paciente, paciente2):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    assert paciente2.get("/api/solicitudes").json() == []
    assert paciente2.get(f"/api/solicitudes/{sol['id']}").status_code == 404
    assert paciente2.post(f"/api/solicitudes/{sol['id']}/cancelar").status_code == 404
    assert paciente2.patch(f"/api/solicitudes/{sol['id']}", json={"titulo": "Hackeada"}).status_code == 404


def test_estudiante_postula_y_paciente_acepta(paciente, estudiante, estudiante2):
    req = estudiante.post("/api/requerimientos", json=REQUERIMIENTO).json()
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()

    r = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"], "requerimiento_id": req["id"],
                                                    "mensaje": "Me sirve para Endodoncia I"})
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["estado"] == "Pendiente" and post["iniciada_por"] == "estudiante"
    assert post["requerimiento"]["tutor"] == "Prof. Ricardo"
    assert post["puede_responder"] is False  # quien postula no se responde a sí mismo

    # La solicitud pasa a "En Revisión" y el paciente la ve con 1 postulación pendiente
    mi = paciente.get(f"/api/solicitudes/{sol['id']}").json()
    assert mi["estado"] == "En Revisión" and mi["postulaciones_pendientes"] == 1
    assert estudiante.get("/api/casos").json()[0]["mi_postulacion_estado"] == "Pendiente"

    # No se puede postular dos veces ni responder la propia postulación
    assert estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).status_code == 409
    assert estudiante.post(f"/api/postulaciones/{post['id']}/responder", json={"accion": "aceptar"}).status_code == 403
    # Otro estudiante no la ve ni la responde
    assert estudiante2.get(f"/api/postulaciones/{post['id']}").status_code == 404

    recibidas = paciente.get("/api/postulaciones?tipo=recibidas").json()
    assert len(recibidas) == 1 and recibidas[0]["puede_responder"] is True

    ok = paciente.post(f"/api/postulaciones/{post['id']}/responder", json={"accion": "aceptar"})
    assert ok.status_code == 200 and ok.json()["estado"] == "Aceptada"
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "Asignada"
    # Ya asignada: sale de la lista de casos disponibles, pero el estudiante aún la ve en su detalle.
    assert estudiante.get("/api/casos").json() == []
    assert estudiante.get(f"/api/casos/{sol['id']}").json()["mi_postulacion_estado"] == "Aceptada"
    assert paciente.post(f"/api/postulaciones/{post['id']}/responder", json={"accion": "rechazar"}).status_code == 409


def test_paciente_solicita_y_estudiante_acepta(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    assert paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).status_code == 422  # falta estudiante
    r = paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"], "estudiante_id": estudiante.id})
    assert r.status_code == 201, r.text
    assert r.json()["iniciada_por"] == "paciente"
    assert paciente.get(f"/api/estudiantes?solicitud_id={sol['id']}").json()[0]["mi_postulacion_estado"] == "Pendiente"

    pendientes = estudiante.get("/api/postulaciones?tipo=recibidas&estado=Pendiente").json()
    assert len(pendientes) == 1 and pendientes[0]["puede_responder"] is True
    assert estudiante.get("/api/resumen").json()["notificaciones"] == 1
    assert estudiante.post(f"/api/postulaciones/{r.json()['id']}/responder", json={"accion": "aceptar"}).status_code == 200
    assert estudiante.get("/api/resumen").json()["notificaciones"] == 0


def test_paciente_no_puede_solicitar_con_solicitud_ajena_ni_a_un_paciente(paciente, paciente2, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    assert paciente2.post("/api/postulaciones",
                          json={"solicitud_id": sol["id"], "estudiante_id": estudiante.id}).status_code == 404
    assert paciente.post("/api/postulaciones",
                         json={"solicitud_id": sol["id"], "estudiante_id": paciente2.id}).status_code == 404


def test_requerimiento_ajeno_se_rechaza(paciente, estudiante, estudiante2):
    req2 = estudiante2.post("/api/requerimientos", json=REQUERIMIENTO).json()
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    r = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"], "requerimiento_id": req2["id"]})
    assert r.status_code == 404


def test_aceptar_rechaza_a_los_demas_y_rechazar_reabre(paciente, estudiante, estudiante2):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p1 = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    p2 = estudiante2.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["postulaciones_pendientes"] == 2

    paciente.post(f"/api/postulaciones/{p1['id']}/responder", json={"accion": "aceptar"})
    assert estudiante2.get(f"/api/postulaciones/{p2['id']}").json()["estado"] == "Rechazada"
    # Asignada: ya no aparece como caso abierto para nuevos estudiantes
    assert estudiante2.get("/api/casos").json() == []

    # Si el aceptado cancela, la solicitud vuelve a estar abierta
    estudiante.post(f"/api/postulaciones/{p1['id']}/cancelar")
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "Abierta"
    assert len(estudiante2.get("/api/casos").json()) == 1


def test_rechazar_la_unica_pendiente_vuelve_a_abierta(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    paciente.post(f"/api/postulaciones/{p['id']}/responder", json={"accion": "rechazar"})
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "Abierta"
    # Una rechazada no se puede reenviar; una cancelada sí
    assert estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).status_code == 409


def test_cancelar_y_reabrir_postulacion(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    assert paciente.post(f"/api/postulaciones/{p['id']}/cancelar").status_code == 403  # no la inició
    assert estudiante.post(f"/api/postulaciones/{p['id']}/cancelar").json()["estado"] == "Cancelada"
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "Abierta"
    again = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]})
    assert again.status_code == 201 and again.json()["id"] == p["id"] and again.json()["estado"] == "Pendiente"


def test_cancelar_solicitud_cancela_lo_pendiente(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    assert paciente.post(f"/api/solicitudes/{sol['id']}/cancelar").json()["estado"] == "Cancelada"
    assert estudiante.get(f"/api/postulaciones/{p['id']}").json()["estado"] == "Cancelada"
    assert estudiante.get("/api/casos").json() == []
    assert estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).status_code == 409
    assert paciente.patch(f"/api/solicitudes/{sol['id']}", json={"titulo": "Nuevo título"}).status_code == 409


def test_flujo_completo_citas_y_avance_del_requerimiento(paciente, estudiante):
    req = estudiante.post("/api/requerimientos", json={**REQUERIMIENTO, "cantidad_requerida": 1}).json()
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p = paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"], "estudiante_id": estudiante.id,
                                                  "requerimiento_id": req["id"]}).json()

    # Sin aceptar todavía no se puede agendar
    assert estudiante.post("/api/citas", json={"postulacion_id": p["id"], "fecha_hora": FUTURO}).status_code == 409
    estudiante.post(f"/api/postulaciones/{p['id']}/responder", json={"accion": "aceptar"})

    cita = estudiante.post("/api/citas", json={"postulacion_id": p["id"], "fecha_hora": FUTURO,
                                               "lugar": "Box 8-B", "notas": "Traer radiografía"})
    assert cita.status_code == 201, cita.text
    assert cita.json()["estudiante"]["nombre"] == "Matías Rojas V."
    assert cita.json()["paciente"]["nombre"] == "Camila Soto M."
    # La fecha pasada se rechaza y el paciente no puede agendar
    assert estudiante.post("/api/citas", json={"postulacion_id": p["id"], "fecha_hora": "2020-01-01T10:00:00"}).status_code == 422
    assert paciente.post("/api/citas", json={"postulacion_id": p["id"], "fecha_hora": FUTURO}).status_code == 403

    assert len(paciente.get("/api/citas?proximas=true").json()) == 1
    assert paciente.get("/api/resumen").json()["citas_proximas"] == 1
    # El paciente solo puede cancelar, no cambiar el lugar
    cid = cita.json()["id"]
    assert paciente.patch(f"/api/citas/{cid}", json={"lugar": "Mi casa"}).status_code == 403
    assert estudiante.patch(f"/api/citas/{cid}", json={"lugar": "Box 9"}).json()["lugar"] == "Box 9"

    hecho = estudiante.post(f"/api/postulaciones/{p['id']}/completar")
    assert hecho.status_code == 200, hecho.text
    assert estudiante.get(f"/api/requerimientos/{req['id']}").json()["estado"] == "Completado"
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "Completada"
    assert estudiante.get("/api/citas?estado=Realizada").json()[0]["id"] == cid
    assert estudiante.post(f"/api/postulaciones/{p['id']}/completar").status_code == 409

    r = paciente.get("/api/resumen").json()
    assert r["tratamientos_completados"] == 1 and r["solicitudes_activas"] == 0
    e = estudiante.get("/api/resumen").json()
    assert e["requerimientos_completados"] == 1 and e["requerimientos_abiertos"] == 0


def test_paciente_puede_cancelar_su_cita(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    p = paciente.post("/api/postulaciones", json={"solicitud_id": sol["id"], "estudiante_id": estudiante.id}).json()
    estudiante.post(f"/api/postulaciones/{p['id']}/responder", json={"accion": "aceptar"})
    cid = estudiante.post("/api/citas", json={"postulacion_id": p["id"], "fecha_hora": FUTURO}).json()["id"]
    assert paciente.patch(f"/api/citas/{cid}", json={"estado": "Cancelada"}).json()["estado"] == "Cancelada"
    assert estudiante.patch(f"/api/citas/{cid}", json={"lugar": "x"}).status_code == 409


def test_resumen_del_estudiante(estudiante, paciente):
    estudiante.post("/api/ramos", json={"ramo": "Endodoncia", "area": "endodoncia"})
    estudiante.post("/api/requerimientos", json=REQUERIMIENTO)
    r = estudiante.get("/api/resumen").json()
    assert r["rol"] == "estudiante" and r["requerimientos_abiertos"] == 1 and r["ramos"] == ["Endodoncia"]
    p = paciente.get("/api/resumen").json()
    assert p["rol"] == "paciente" and p["solicitudes_activas"] == 0


def test_estudiantes_para_el_paciente_con_filtros(paciente, estudiante, estudiante2):
    estudiante.put("/api/perfil/estudiante", json={"comuna_atencion": "Recoleta", "disponibilidad": "Martes por la mañana"})
    estudiante2.put("/api/perfil/estudiante", json={"comuna_atencion": "Ñuñoa", "disponibilidad": "Viernes tarde"})
    estudiante.post("/api/requerimientos", json=REQUERIMIENTO)
    estudiante.post("/api/ramos", json={"ramo": "Endodoncia I", "area": "endodoncia", "tutor": "Prof. Ricardo"})

    todos = paciente.get("/api/estudiantes").json()
    assert len(todos) == 2
    e = next(x for x in todos if x["id"] == estudiante.id)
    assert e["areas"] == ["endodoncia"] and e["tutores"] == ["Prof. Ricardo"] and e["ramos"] == ["Endodoncia I"]
    assert e["requerimientos_abiertos"][0]["restantes"] == 2

    assert [x["id"] for x in paciente.get("/api/estudiantes?area=endodoncia").json()] == [estudiante.id]
    assert [x["id"] for x in paciente.get("/api/estudiantes?comuna=uñoa").json()] == [estudiante2.id]
    assert [x["id"] for x in paciente.get("/api/estudiantes?turno=manana").json()] == [estudiante.id]
    assert [x["id"] for x in paciente.get("/api/estudiantes?turno=tarde").json()] == [estudiante2.id]
    assert paciente.get(f"/api/estudiantes/{estudiante.id}").status_code == 200
    assert paciente.get(f"/api/estudiantes/{paciente.id}").status_code == 404


def test_catalogos_son_publicos(client):
    r = client.get("/api/catalogos").json()
    assert {"clave": "endodoncia", "nombre": "Endodoncia"} in r["areas"]
    assert "Lunes" in r["dias_semana"]


# ---------- compatibilidad con la tabla `solicitudes` del equipo ----------
def _estado_en_bd(solicitud_id):
    """Lo que realmente queda guardado en la columna del equipo."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        return db.get(models.Solicitud, solicitud_id).estado
    finally:
        db.close()


def test_solicitud_creada_por_otra_app_sin_detalle_funciona(client, paciente, estudiante):
    """Una fila insertada solo con las columnas del equipo debe verse y poder gestionarse."""
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    fila = models.Solicitud(paciente_id=paciente.id, descripcion="Me duele una muela desde hace dos dias",
                            comuna="Maipú")
    db.add(fila)
    db.commit()
    sid = fila.id
    db.close()

    caso = estudiante.get("/api/casos").json()[0]
    assert caso["id"] == sid and caso["area"] == "diagnostico" and caso["urgente"] is False
    assert caso["titulo"].startswith("Me duele una muela") and caso["comuna"] == "Maipú"

    p = estudiante.post("/api/postulaciones", json={"solicitud_id": sid}).json()
    paciente.post(f"/api/postulaciones/{p['id']}/responder", json={"accion": "aceptar"})
    assert estudiante.post(f"/api/postulaciones/{p['id']}/completar").status_code == 200  # crea el detalle
    assert paciente.get(f"/api/solicitudes/{sid}").json()["estado"] == "Completada"


def test_el_estado_guardado_respeta_el_check_del_equipo(paciente, estudiante):
    sol = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    assert _estado_en_bd(sol["id"]) == "Buscando"
    p = estudiante.post("/api/postulaciones", json={"solicitud_id": sol["id"]}).json()
    assert _estado_en_bd(sol["id"]) == "Buscando"  # 'En Revisión' solo existe en la API
    assert paciente.get(f"/api/solicitudes/{sol['id']}").json()["estado"] == "En Revisión"
    paciente.post(f"/api/postulaciones/{p['id']}/responder", json={"accion": "aceptar"})
    assert _estado_en_bd(sol["id"]) == "Asignado"
    estudiante.post(f"/api/postulaciones/{p['id']}/completar")
    assert _estado_en_bd(sol["id"]) == "Asignado"  # 'Completada' solo existe en la API
    otra = paciente.post("/api/solicitudes", json=SOLICITUD).json()
    paciente.post(f"/api/solicitudes/{otra['id']}/cancelar")
    assert _estado_en_bd(otra["id"]) == "Cancelado"


def test_comuna_vacia_se_guarda_como_sin_especificar(paciente):
    sin_comuna = {k: v for k, v in SOLICITUD.items() if k != "comuna"}
    sol = paciente.post("/api/solicitudes", json=sin_comuna).json()
    assert sol["comuna"] is None  # la API no expone el texto de relleno
