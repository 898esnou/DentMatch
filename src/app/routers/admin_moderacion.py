"""
Panel de administración: moderación (solo rol admin).

Reportes
- GET  /api/admin/reportes?estado=Pendiente|Resuelto   bandeja (los automáticos primero)
- GET  /api/admin/reportes/{id}                        detalle con la evidencia
- POST /api/admin/reportes/{id}/resolver               {decision: baneo|suspension|descartar,
                                                        dias?, mensaje?, nota?}
Cuentas
- GET  /api/admin/cuentas?q=&estado=                   personas con su estado y advertencias
- POST /api/admin/cuentas/{id}/levantar-sancion        reactiva una cuenta baneada o suspendida
Resumen
- GET  /api/admin/resumen                              números para la portada del panel

El admin NO lee los chats directamente: ve la evidencia que se copió en cada reporte.
(La verificación de estudiantes está en admin.py.)
"""
import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, sanciones
from app.auth import require_rol
from app.catalogos import ESTADOS_CUENTA, ESTADOS_REPORTE
from app.database import get_db
from app.schemas_dominio import (
    BloqueadoEvidenciaOut, CuentaAdminOut, DecisionIn, MensajeEvidenciaOut, PersonaAdminOut,
    ReporteDetalleOut, ReporteListaOut, ResolucionOut, ResumenAdminOut,
)
from app.servicios import ahora
from app.utils import ESCAPE_LIKE, patron_contiene

router = APIRouter(prefix="/api/admin", tags=["admin: moderación"])

solo_admin = require_rol("admin")


# ---------------------------------------------------------------- piezas comunes
def _estado_efectivo(fila: Optional[models.EstadoCuenta]) -> str:
    """Estado real de la cuenta: 'activo' si no tiene fila o si su time-out ya terminó."""
    if fila is None:
        return "activo"
    # Un time-out que ya venció cuenta como activo aunque nadie haya vuelto a entrar todavía.
    if fila.estado == "suspendido" and fila.suspendido_hasta and fila.suspendido_hasta <= ahora():
        return "activo"
    return fila.estado


def _estado_cuenta(db: Session, usuario_id: int) -> str:
    return _estado_efectivo(db.get(models.EstadoCuenta, usuario_id))


def _personas(db: Session, usuarios) -> dict:
    """PersonaAdminOut de varios usuarios con 2 consultas en total (no 2 por persona)."""
    ids = list({u.id for u in usuarios})
    if not ids:
        return {}
    filas = {
        e.usuario_id: e
        for e in db.query(models.EstadoCuenta).filter(models.EstadoCuenta.usuario_id.in_(ids)).all()
    }
    advertencias = sanciones.contar_advertencias_varios(db, ids)
    return {
        u.id: PersonaAdminOut(
            id=u.id, nombre=u.nombre_completo, rol=u.rol,
            estado_cuenta=_estado_efectivo(filas.get(u.id)),
            advertencias=advertencias.get(u.id, 0),
        )
        for u in usuarios
    }


def _lista_out(r: models.Reporte, personas: dict) -> ReporteListaOut:
    return ReporteListaOut(
        id=r.id, origen=r.origen, estado=r.estado, decision=r.decision, motivo=r.motivo,
        fecha_creacion=r.fecha_creacion,
        reportado=personas[r.reportado_id],
        reportante=r.reportante.nombre_completo if r.reportante else None,
    )


def _reporte_o_404(db: Session, reporte_id: int) -> models.Reporte:
    r = db.get(models.Reporte, reporte_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return r


# ---------------------------------------------------------------- reportes
@router.get("/reportes", response_model=List[ReporteListaOut])
def listar_reportes(
    estado: Optional[str] = Query("Pendiente"),
    _: models.Usuario = Depends(solo_admin),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_REPORTE:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = db.query(models.Reporte).options(
        joinedload(models.Reporte.reportado), joinedload(models.Reporte.reportante)
    )
    if estado:
        consulta = consulta.filter(models.Reporte.estado == estado)
    reportes = consulta.order_by(models.Reporte.id.desc()).all()
    # Primero los automáticos (ya hay una cuenta baneada esperando decisión), luego los más nuevos.
    reportes.sort(key=lambda r: 0 if r.origen == "automatico" else 1)
    personas = _personas(db, [r.reportado for r in reportes])
    return [_lista_out(r, personas) for r in reportes]


@router.get("/reportes/{reporte_id}", response_model=ReporteDetalleOut)
def ver_reporte(
    reporte_id: int,
    _: models.Usuario = Depends(solo_admin),
    db: Session = Depends(get_db),
):
    r = _reporte_o_404(db, reporte_id)
    evidencia = json.loads(r.evidencia) if r.evidencia else {}

    # Nombres de quienes hablaron: el reportado y la otra persona de la conversación.
    p = db.get(models.Postulacion, r.postulacion_id) if r.postulacion_id else None
    otra = None
    if p is not None:
        paciente, estudiante = p.solicitud.paciente, p.estudiante
        otra = estudiante if r.reportado_id == paciente.id else paciente
    nombres = {r.reportado_id: r.reportado.nombre_completo}
    if otra is not None:
        nombres[otra.id] = otra.nombre_completo

    previos = (
        db.query(func.count(models.Reporte.id))
        .filter(models.Reporte.reportado_id == r.reportado_id, models.Reporte.id != r.id)
        .scalar()
    )
    resolucion = None
    if r.estado == "Resuelto":
        resolvio = db.get(models.Usuario, r.resuelto_por) if r.resuelto_por else None
        resolucion = ResolucionOut(
            decision=r.decision, nota=r.nota_admin, dias=r.suspension_dias,
            resuelto_por=resolvio.nombre_completo if resolvio else None, fecha=r.fecha_resolucion,
        )

    return ReporteDetalleOut(
        **_lista_out(r, _personas(db, [r.reportado])).model_dump(),
        otra_persona=otra.nombre_completo if otra else None,
        conversacion=p.solicitud.titulo if p else None,
        reportes_previos=previos,
        mensajes=[
            MensajeEvidenciaOut(
                de_reportado=m["autor_id"] == r.reportado_id,
                autor=nombres.get(m["autor_id"], "Otra persona"),
                contenido=m["contenido"],
                fecha=datetime.fromisoformat(m["fecha"]),
            )
            for m in evidencia.get("mensajes", [])
        ],
        bloqueados=[
            BloqueadoEvidenciaOut(
                contenido=b["contenido"], categoria=b["categoria"], fuente=b["fuente"],
                fecha=datetime.fromisoformat(b["fecha"]),
            )
            for b in evidencia.get("mensajes_bloqueados", [])
        ],
        resolucion=resolucion,
    )


@router.post("/reportes/{reporte_id}/resolver", response_model=ReporteDetalleOut)
def resolver_reporte(
    reporte_id: int,
    datos: DecisionIn,
    admin: models.Usuario = Depends(solo_admin),
    db: Session = Depends(get_db),
):
    r = _reporte_o_404(db, reporte_id)
    try:
        sanciones.resolver_reporte(
            db, r, admin, decision=datos.decision, dias=datos.dias, mensaje=datos.mensaje, nota=datos.nota
        )
    except sanciones.DecisionInvalida as error:
        raise HTTPException(status_code=409 if r.estado != "Pendiente" else 422, detail=str(error))
    db.commit()
    return ver_reporte(reporte_id, admin, db)


# ---------------------------------------------------------------- cuentas
@router.get("/cuentas", response_model=List[CuentaAdminOut])
def listar_cuentas(
    q: Optional[str] = Query(None, description="Nombre o correo"),
    estado: Optional[str] = Query(None),
    _: models.Usuario = Depends(solo_admin),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS_CUENTA:
        raise HTTPException(status_code=422, detail="Estado inválido")
    U, E = models.Usuario, models.EstadoCuenta
    base = db.query(U).filter(U.rol.in_(("estudiante", "paciente")))
    if q and q.strip():
        patron = patron_contiene(q)
        base = base.filter(U.nombre_completo.ilike(patron, escape=ESCAPE_LIKE) | U.correo.ilike(patron, escape=ESCAPE_LIKE))
    # Las sancionadas se buscan aparte para que ninguna quede fuera del tope de 200 por ser antigua.
    sancionadas = base.join(E, E.usuario_id == U.id).filter(E.estado != "activo").order_by(U.id.desc()).all()
    ids_sancionadas = {u.id for u in sancionadas}
    resto = []
    if estado != "baneado" and estado != "suspendido":
        resto = [u for u in base.order_by(U.id.desc()).limit(200 + len(ids_sancionadas)).all()
                 if u.id not in ids_sancionadas][:200]
    usuarios = sancionadas + resto

    ids = [u.id for u in usuarios]
    filas = {e.usuario_id: e for e in db.query(E).filter(E.usuario_id.in_(ids)).all()} if ids else {}
    advertencias = sanciones.contar_advertencias_varios(db, ids)
    reportes = dict(
        db.query(models.Reporte.reportado_id, func.count(models.Reporte.id))
        .filter(models.Reporte.reportado_id.in_(ids))
        .group_by(models.Reporte.reportado_id)
        .all()
    ) if ids else {}

    salida = []
    for u in usuarios:
        fila = filas.get(u.id)
        actual = _estado_efectivo(fila)
        if estado and actual != estado:
            continue
        salida.append(CuentaAdminOut(
            id=u.id, nombre_completo=u.nombre_completo, correo=u.correo, rol=u.rol,
            estado_cuenta=actual,
            suspendido_hasta=fila.suspendido_hasta if fila and actual == "suspendido" else None,
            motivo=fila.motivo if fila and actual != "activo" else None,
            advertencias=advertencias.get(u.id, 0),
            reportes_recibidos=reportes.get(u.id, 0),
        ))
    # Las cuentas sancionadas primero (es lo que el admin suele buscar), luego las más nuevas.
    salida.sort(key=lambda c: (0 if c.estado_cuenta != "activo" else 1, -c.id))
    return salida


@router.post("/cuentas/{usuario_id}/levantar-sancion", response_model=CuentaAdminOut)
def levantar_sancion(
    usuario_id: int,
    _: models.Usuario = Depends(solo_admin),
    db: Session = Depends(get_db),
):
    u = db.get(models.Usuario, usuario_id)
    if u is None or u.rol not in ("estudiante", "paciente"):
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    if _estado_cuenta(db, u.id) == "activo":
        raise HTTPException(status_code=409, detail="Esta cuenta no tiene ninguna sanción")
    sanciones.levantar_sancion(db, u)
    db.commit()
    return CuentaAdminOut(
        id=u.id, nombre_completo=u.nombre_completo, correo=u.correo, rol=u.rol, estado_cuenta="activo",
        advertencias=0,
        reportes_recibidos=db.query(func.count(models.Reporte.id)).filter(models.Reporte.reportado_id == u.id).scalar(),
    )


# ---------------------------------------------------------------- resumen
@router.get("/resumen", response_model=ResumenAdminOut)
def resumen(_: models.Usuario = Depends(solo_admin), db: Session = Depends(get_db)):
    R, E = models.Reporte, models.EstadoCuenta
    pendientes = db.query(R).filter(R.estado == "Pendiente")
    desde = ahora() - timedelta(days=30)
    return ResumenAdminOut(
        reportes_pendientes=pendientes.count(),
        reportes_automaticos_pendientes=pendientes.filter(R.origen == "automatico").count(),
        reportes_resueltos_30d=db.query(R).filter(R.estado == "Resuelto", R.fecha_resolucion >= desde).count(),
        cuentas_baneadas=db.query(E).filter(E.estado == "baneado").count(),
        cuentas_suspendidas=db.query(E).filter(
            E.estado == "suspendido", (E.suspendido_hasta.is_(None)) | (E.suspendido_hasta > ahora())
        ).count(),
        verificaciones_pendientes=db.query(models.PerfilEstudiante)
        .filter(models.PerfilEstudiante.estado_verificacion == "En Verificación").count(),
    )
