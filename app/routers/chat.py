"""
Chat de coordinación entre paciente y estudiante.

Cada postulación es una conversación y solo la ven esas dos personas.
- Se puede escribir mientras la postulación está Aceptada y el tratamiento sigue en curso.
- Si se cancela o el tratamiento se completa, queda de solo lectura y el historial
  se borra solo a los 30 días del cierre (ver DIAS_HISTORIAL).
- Cualquiera de las dos personas puede archivarla: queda de solo lectura (y el historial
  también se borra a los 30 días), pero solo quien la archivó puede reabrirla.

Endpoints:
- GET  /api/chat/conversaciones             mis conversaciones (con no leídos)
- GET  /api/chat/{postulacion_id}/mensajes  el hilo; marca como leídos los de la otra persona
- POST /api/chat/{postulacion_id}/mensajes  enviar un mensaje (pasa por la moderación)
- POST /api/chat/{postulacion_id}/reportar  reportar a la otra persona (tras unos mensajes)
- POST /api/chat/{postulacion_id}/archivar  archivar la conversación (solo lectura para las dos)
- POST /api/chat/{postulacion_id}/reabrir   reabrirla (solo quien la archivó)

Moderación (Épica 5): un mensaje con insultos, insinuaciones o fuera de tema NO se envía
(app/moderacion.py). Insultos e insinuaciones suman advertencias; a la 3ª la cuenta se
banea y se crea un reporte automático (app/sanciones.py).

No usa WebSockets: el portal consulta cada pocos segundos (así funciona también en Vercel).
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, moderacion, sanciones
from app.auth import exigir_estudiante_verificado, require_rol
from app.database import get_db
from app.schemas_dominio import (
    ConversacionOut, HiloOut, MensajeIn, MensajeOut, ParticipanteOut, ReporteCreadoOut, ReporteIn,
)
from app.servicios import ahora
from app.utils import nombre_corto

router = APIRouter(prefix="/api/chat", tags=["chat"])

ambos_roles = require_rol("estudiante", "paciente")

DIAS_HISTORIAL = 30        # días que se conserva el historial después de cerrada la conversación
MAX_MENSAJES_HILO = 500    # tope de mensajes que devuelve un hilo


# ---------- reglas de la conversación ----------
def _en_curso(p: models.Postulacion) -> bool:
    """Postulación Aceptada y tratamiento todavía no terminado."""
    return p.estado == "Aceptada" and p.solicitud.estado_api == "Asignada"


def _archivada(p: models.Postulacion) -> bool:
    """Alguien la archivó (solo cuenta mientras la conversación seguiría abierta)."""
    return p.archivo_chat is not None and _en_curso(p)


def _puede_escribir(p: models.Postulacion) -> bool:
    """Abierta = en curso y sin archivar."""
    return _en_curso(p) and p.archivo_chat is None


def _fecha_cierre(p: models.Postulacion) -> Optional[datetime]:
    """Cuándo se cerró la conversación (cancelada o terminada). None si sigue abierta."""
    if p.estado == "Cancelada":
        return p.fecha_respuesta or p.fecha_creacion
    if p.solicitud.estado_api == "Completada":
        return p.solicitud.detalle.completada_en
    if _archivada(p):
        return p.archivo_chat.fecha
    return None


def _se_borra_el(p: models.Postulacion) -> Optional[datetime]:
    cierre = _fecha_cierre(p)
    return cierre + timedelta(days=DIAS_HISTORIAL) if cierre else None


def _borrar_vencidos(db: Session, postulaciones: List[models.Postulacion]) -> None:
    """Borra el historial de las conversaciones cerradas hace más de 30 días."""
    for p in postulaciones:
        limite = _se_borra_el(p)
        if limite is not None and limite <= ahora():
            db.query(models.Mensaje).filter(models.Mensaje.postulacion_id == p.id).delete()
    db.commit()


# ---------- consultas ----------
def _base(db: Session):
    return (
        db.query(models.Postulacion)
        .join(models.Solicitud, models.Postulacion.solicitud_id == models.Solicitud.id)
        .options(
            joinedload(models.Postulacion.solicitud).joinedload(models.Solicitud.paciente),
            joinedload(models.Postulacion.estudiante),
            joinedload(models.Postulacion.cierre_moderacion),
            joinedload(models.Postulacion.archivo_chat),
        )
    )


def _solo_mias(consulta, usuario: models.Usuario):
    if usuario.rol == "estudiante":
        return consulta.filter(models.Postulacion.estudiante_id == usuario.id)
    return consulta.filter(models.Solicitud.paciente_id == usuario.id)


def _visible(db: Session, postulacion_id: int, usuario: models.Usuario) -> models.Postulacion:
    p = _solo_mias(_base(db), usuario).filter(models.Postulacion.id == postulacion_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return p


# ---------- conversión a los esquemas de salida ----------
def _conversacion_out(p, usuario, no_leidos=0, ultimo=None) -> ConversacionOut:
    otra = p.solicitud.paciente if usuario.rol == "estudiante" else p.estudiante
    detenida = p.cierre_moderacion is not None
    archivada = _archivada(p)
    return ConversacionOut(
        archivada=archivada,
        archivada_por_mi=archivada and p.archivo_chat.archivada_por == usuario.id,
        cerrada_por_moderacion=detenida,
        mensaje_cierre=sanciones.mensaje_de_cierre(usuario.rol) if detenida else None,
        postulacion_id=p.id,
        solicitud_codigo=p.solicitud.codigo,
        titulo=p.solicitud.titulo,
        otra_parte=ParticipanteOut(id=otra.id, nombre=nombre_corto(otra.nombre_completo)),
        puede_escribir=_puede_escribir(p),
        no_leidos=no_leidos,
        ultimo_mensaje=ultimo.contenido if ultimo else None,
        ultima_fecha=ultimo.fecha_creacion if ultimo else None,
        se_borra_el=_se_borra_el(p),
    )


def _mensaje_out(m: models.Mensaje, usuario: models.Usuario) -> MensajeOut:
    return MensajeOut(
        id=m.id,
        mio=m.autor_id == usuario.id,
        contenido=m.contenido,
        fecha_creacion=m.fecha_creacion,
        leido=m.leido_en is not None,
    )


# ---------- endpoints ----------
@router.get("/conversaciones", response_model=List[ConversacionOut])
def listar_conversaciones(
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    # Candidatas: las aceptadas y las que ya tienen mensajes (cerradas con historial).
    con_mensajes = db.query(models.Mensaje.postulacion_id)
    postulaciones = (
        _solo_mias(_base(db), usuario)
        .filter(
            (models.Postulacion.estado == "Aceptada")
            | models.Postulacion.id.in_(con_mensajes)
            | models.Postulacion.id.in_(db.query(models.CierreModeracion.postulacion_id))
        )
        .all()
    )
    _borrar_vencidos(db, postulaciones)
    ids = [p.id for p in postulaciones]
    if not ids:
        return []

    # Mensajes sin leer de la otra persona, por conversación.
    no_leidos = dict(
        db.query(models.Mensaje.postulacion_id, func.count(models.Mensaje.id))
        .filter(
            models.Mensaje.postulacion_id.in_(ids),
            models.Mensaje.autor_id != usuario.id,
            models.Mensaje.leido_en.is_(None),
        )
        .group_by(models.Mensaje.postulacion_id)
        .all()
    )
    # Último mensaje de cada conversación.
    id_ultimos = (
        db.query(func.max(models.Mensaje.id))
        .filter(models.Mensaje.postulacion_id.in_(ids))
        .group_by(models.Mensaje.postulacion_id)
    )
    ultimos = {
        m.postulacion_id: m
        for m in db.query(models.Mensaje).filter(models.Mensaje.id.in_(id_ultimos)).all()
    }

    salida = []
    for p in postulaciones:
        # Una conversación cerrada y sin historial ya no tiene nada que mostrar.
        detenida_vigente = p.cierre_moderacion is not None and (_se_borra_el(p) or ahora()) > ahora()
        archivada_vigente = _archivada(p) and (_se_borra_el(p) or ahora()) > ahora()
        if not _puede_escribir(p) and p.id not in ultimos and not detenida_vigente and not archivada_vigente:
            continue
        salida.append(_conversacion_out(p, usuario, no_leidos.get(p.id, 0), ultimos.get(p.id)))
    # Primero las de mensajes más recientes.
    salida.sort(key=lambda c: (c.ultima_fecha or datetime.min, c.postulacion_id), reverse=True)
    return salida


@router.get("/{postulacion_id}/mensajes", response_model=HiloOut)
def ver_hilo(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    p = _visible(db, postulacion_id, usuario)
    _borrar_vencidos(db, [p])

    # Abrir el hilo = leer lo que escribió la otra persona.
    db.query(models.Mensaje).filter(
        models.Mensaje.postulacion_id == p.id,
        models.Mensaje.autor_id != usuario.id,
        models.Mensaje.leido_en.is_(None),
    ).update({"leido_en": ahora()}, synchronize_session=False)
    aviso = sanciones.aviso_para_receptor(db, p.id, usuario.id)
    db.commit()

    total = db.query(func.count(models.Mensaje.id)).filter(models.Mensaje.postulacion_id == p.id).scalar()
    recientes = (
        db.query(models.Mensaje)
        .filter(models.Mensaje.postulacion_id == p.id)
        .order_by(models.Mensaje.id.desc())
        .limit(MAX_MENSAJES_HILO)
        .all()
    )
    recientes.reverse()  # del más antiguo al más nuevo
    return HiloOut(
        conversacion=_conversacion_out(p, usuario, 0, recientes[-1] if recientes else None),
        mensajes=[_mensaje_out(m, usuario) for m in recientes],
        puede_reportar=(
            total >= sanciones.MIN_MENSAJES_REPORTAR
            and not sanciones.tiene_reporte_pendiente(db, p.id, usuario.id)
        ),
        aviso_moderacion=aviso,
    )


@router.post("/{postulacion_id}/mensajes", response_model=MensajeOut, status_code=status.HTTP_201_CREATED)
def enviar_mensaje(
    postulacion_id: int,
    datos: MensajeIn,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    exigir_estudiante_verificado(usuario)  # un estudiante sin verificar no interactúa con pacientes
    p = _visible(db, postulacion_id, usuario)
    if not _puede_escribir(p):
        motivo = "archivada" if _archivada(p) else "cerrada"
        raise HTTPException(status_code=409, detail=f"Esta conversación está {motivo}: ya no admite mensajes")
    texto = datos.contenido.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Escribe un mensaje")

    # Moderación: el mensaje bloqueado no se guarda como mensaje, así nunca le llega a la otra persona.
    previos = (
        db.query(models.Mensaje.contenido)
        .filter(models.Mensaje.postulacion_id == p.id)
        .order_by(models.Mensaje.id.desc())
        .limit(moderacion.CONTEXTO_MENSAJES)
        .all()
    )
    resultado = moderacion.moderar(texto, [c for (c,) in reversed(previos)])
    if not resultado.permitido:
        bloqueo = sanciones.registrar_bloqueo(db, usuario, p, resultado, texto)
        db.commit()
        if bloqueo.baneado:
            raise HTTPException(status_code=403, detail=sanciones.MENSAJE_BANEO)
        aviso = moderacion.MENSAJES_AL_EMISOR[resultado.categoria]
        if bloqueo.numero is not None:
            aviso += (
                f" Advertencia {bloqueo.numero} de {sanciones.MAX_ADVERTENCIAS}: "
                f"al llegar a {sanciones.MAX_ADVERTENCIAS} tu cuenta será suspendida."
            )
        raise HTTPException(status_code=422, detail=aviso)

    mensaje = models.Mensaje(
        postulacion_id=p.id, autor_id=usuario.id, contenido=texto, fecha_creacion=ahora()
    )
    db.add(mensaje)
    db.commit()
    db.refresh(mensaje)
    return _mensaje_out(mensaje, usuario)


@router.post("/{postulacion_id}/reportar", response_model=ReporteCreadoOut, status_code=status.HTTP_201_CREATED)
def reportar(
    postulacion_id: int,
    datos: ReporteIn,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    """Reporta a la otra persona. Se habilita cuando la conversación ya tiene algunos mensajes."""
    p = _visible(db, postulacion_id, usuario)
    total = db.query(func.count(models.Mensaje.id)).filter(models.Mensaje.postulacion_id == p.id).scalar()
    if total < sanciones.MIN_MENSAJES_REPORTAR:
        raise HTTPException(status_code=409, detail="Aún no hay suficientes mensajes para reportar esta conversación")
    if sanciones.tiene_reporte_pendiente(db, p.id, usuario.id):
        raise HTTPException(status_code=409, detail="Ya reportaste esta conversación: un administrador la está revisando")
    reportado = p.solicitud.paciente if usuario.rol == "estudiante" else p.estudiante
    reporte = sanciones.crear_reporte(
        db, postulacion=p, reportado=reportado, reportante=usuario, origen="usuario", motivo=datos.motivo.strip()
    )
    db.commit()
    db.refresh(reporte)
    return ReporteCreadoOut(id=reporte.id, mensaje="Gracias. Un administrador revisará tu reporte.")


@router.post("/{postulacion_id}/archivar", response_model=ConversacionOut)
def archivar(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    """Cierra el chat para las dos personas (solo lectura). La postulación y las citas no cambian."""
    p = _visible(db, postulacion_id, usuario)
    if _archivada(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está archivada")
    if not _en_curso(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está cerrada")
    p.archivo_chat = models.ConversacionArchivada(archivada_por=usuario.id, fecha=ahora())
    otra = p.solicitud.paciente if usuario.rol == "estudiante" else p.estudiante
    sanciones.avisar(db, otra.id, (
        f"«{p.solicitud.titulo}»: la otra persona archivó la conversación, así que ya no se pueden "
        "enviar mensajes. Si necesitas coordinar algo, puedes pedirle que la reabra."
    ))
    db.commit()
    db.refresh(p)
    return _conversacion_out(p, usuario)


@router.post("/{postulacion_id}/reabrir", response_model=ConversacionOut)
def reabrir(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    """Reabre una conversación archivada. Solo puede hacerlo quien la archivó."""
    p = _visible(db, postulacion_id, usuario)
    if not _archivada(p):
        raise HTTPException(status_code=409, detail="Esta conversación no está archivada")
    if p.archivo_chat.archivada_por != usuario.id:
        raise HTTPException(status_code=403, detail="Solo quien archivó la conversación puede reabrirla")
    p.archivo_chat = None
    otra = p.solicitud.paciente if usuario.rol == "estudiante" else p.estudiante
    sanciones.avisar(db, otra.id, f"«{p.solicitud.titulo}»: la otra persona reabrió la conversación. Ya puedes escribir de nuevo.")
    db.commit()
    db.refresh(p)
    return _conversacion_out(p, usuario)
