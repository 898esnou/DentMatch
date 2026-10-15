"""
GET /api/resumen -> los números de la cabecera de cada portal, según el rol.
`notificaciones` cuenta lo que requiere una acción de este usuario
(postulaciones por responder), para el globo de la campana.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.database import get_db
from app.schemas_dominio import ResumenOut
from app.servicios import ahora

router = APIRouter(prefix="/api/resumen", tags=["resumen"])


@router.get("", response_model=ResumenOut)
def resumen(
    usuario: models.Usuario = Depends(require_rol("estudiante", "paciente")),
    db: Session = Depends(get_db),
):
    P, S, C, R = models.Postulacion, models.Solicitud, models.Cita, models.Requerimiento
    proximas = (C.estado == "Agendada") & (C.fecha_hora >= ahora())

    if usuario.rol == "estudiante":
        def contar_req(estado):
            return db.query(func.count(R.id)).filter(
                R.estudiante_id == usuario.id, R.estado == estado
            ).scalar()

        def contar_post(iniciada_por_paciente: bool):
            condicion = (P.iniciada_por == "paciente") if iniciada_por_paciente else (P.iniciada_por == "estudiante")
            return db.query(func.count(P.id)).filter(
                P.estudiante_id == usuario.id, P.estado == "Pendiente", condicion
            ).scalar()

        recibidas = contar_post(True)
        return ResumenOut(
            rol="estudiante",
            requerimientos_abiertos=contar_req("Abierto"),
            requerimientos_completados=contar_req("Completado"),
            postulaciones_recibidas=recibidas,
            ramos=[
                r.ramo for r in db.query(models.RamoEstudiante)
                .filter(models.RamoEstudiante.estudiante_id == usuario.id)
                .order_by(models.RamoEstudiante.id)
            ],
            postulaciones_pendientes=contar_post(False),
            citas_proximas=db.query(func.count(C.id))
            .join(P, C.postulacion_id == P.id)
            .filter(P.estudiante_id == usuario.id, proximas)
            .scalar(),
            notificaciones=recibidas,
        )

    # paciente
    # El estado de la API se deriva (ver Solicitud.estado_api), así que se cuenta en Python.
    mis_estados = [
        s.estado_api for s in db.query(S).filter(S.paciente_id == usuario.id).all()
    ]

    def contar_solicitudes(*estados):
        return sum(1 for e in mis_estados if e in estados)

    def contar_post(iniciada_por_paciente: bool):
        condicion = (P.iniciada_por == "paciente") if iniciada_por_paciente else (P.iniciada_por == "estudiante")
        return (
            db.query(func.count(P.id))
            .join(S, P.solicitud_id == S.id)
            .filter(S.paciente_id == usuario.id, P.estado == "Pendiente", condicion)
            .scalar()
        )

    por_responder = contar_post(False)  # estudiantes que postularon a mis solicitudes
    return ResumenOut(
        rol="paciente",
        solicitudes_activas=contar_solicitudes("Abierta", "En Revisión", "Asignada"),
        tratamientos_completados=contar_solicitudes("Completada"),
        postulaciones_pendientes=contar_post(True),
        citas_proximas=db.query(func.count(C.id))
        .join(P, C.postulacion_id == P.id)
        .join(S, P.solicitud_id == S.id)
        .filter(S.paciente_id == usuario.id, proximas)
        .scalar(),
        notificaciones=por_responder,
    )
