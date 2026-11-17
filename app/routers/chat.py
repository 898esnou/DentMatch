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
- POST /api/chat/{postulacion_id}/bloquear     bloquear a la otra persona (solo lectura para las dos)
- POST /api/chat/{postulacion_id}/desbloquear  desbloquear (solo quien bloqueó)

Moderación (Épica 5): un mensaje con insultos, insinuaciones o fuera de tema NO se envía
(app/moderacion.py). Insultos e insinuaciones suman advertencias; a la 3ª la cuenta se
banea y se crea un reporte automático (app/sanciones.py).

No usa WebSockets: el portal consulta cada pocos segundos (así funciona también en Vercel).
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, contains_eager, joinedload

from app import models, moderacion, sanciones
from app.auth import exigir_estudiante_verificado, require_rol
from app.database import get_db
from app.schemas_dominio import (
    ConversacionOut, HiloOut, MensajeInapropiadoOut, MensajeIn, MensajeOut, ParticipanteOut,
    ReporteCreadoOut, ReporteIn,
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


def _bloqueada(p: models.Postulacion) -> bool:
    """Alguien bloqueó al otro (solo cuenta mientras la conversación seguiría abierta)."""
    return p.bloqueo_chat is not None and _en_curso(p)


def _puede_escribir(p: models.Postulacion) -> bool:
    """Abierta = en curso, sin archivar y sin bloqueo."""
    return _en_curso(p) and p.archivo_chat is None and p.bloqueo_chat is None


def _fecha_cierre(p: models.Postulacion) -> Optional[datetime]:
    """Cuándo se cerró la conversación (cancelada o terminada). None si sigue abierta."""
    if p.estado == "Cancelada":
        return p.fecha_respuesta or p.fecha_creacion
    if p.solicitud.estado_api == "Completada":
        return p.solicitud.detalle.completada_en
    if _bloqueada(p):
        return p.bloqueo_chat.fecha
    if _archivada(p):
        return p.archivo_chat.fecha
    return None


def _se_borra_el(p: models.Postulacion) -> Optional[datetime]:
    cierre = _fecha_cierre(p)
    return cierre + timedelta(days=DIAS_HISTORIAL) if cierre else None


def _historial_vigente(p: models.Postulacion) -> bool:
    """True mientras el historial no deba borrarse (conversación abierta o cerrada hace menos de 30 días)."""
    limite = _se_borra_el(p)
    return limite is None or limite > ahora()


def _otra_parte(p: models.Postulacion, usuario: models.Usuario) -> models.Usuario:
    """La otra persona de la conversación (el paciente si escribo como estudiante, y viceversa)."""
    return p.solicitud.paciente if usuario.rol == "estudiante" else p.estudiante


def _borrar_vencidos(db: Session, postulaciones: List[models.Postulacion]) -> None:
    """Borra el historial de las conversaciones cerradas hace más de 30 días."""
    vencidas = [p.id for p in postulaciones if not _historial_vigente(p)]
    if vencidas:
        db.query(models.Mensaje).filter(models.Mensaje.postulacion_id.in_(vencidas)).delete(synchronize_session=False)
        db.commit()


# ---------- consultas ----------
def _base(db: Session):
    """
    Postulaciones con todo lo que necesita una conversación, en UNA sola consulta
    (cada consulta extra son ~100 ms con la base en la nube y el chat se consulta cada pocos segundos).
    """
    return (
        db.query(models.Postulacion)
        .join(models.Solicitud, models.Postulacion.solicitud_id == models.Solicitud.id)
        .options(
            # contains_eager reutiliza el JOIN de arriba (sin un segundo JOIN a solicitudes).
            contains_eager(models.Postulacion.solicitud).joinedload(models.Solicitud.paciente),
            # Las postulaciones de la solicitud solo hacen falta si sigue "Buscando" (estado_api):
            # se cargan recién si se usan, en vez de una consulta extra en cada petición.
            contains_eager(models.Postulacion.solicitud).lazyload(models.Solicitud.postulaciones),
            joinedload(models.Postulacion.estudiante),
            joinedload(models.Postulacion.cierre_moderacion),
            joinedload(models.Postulacion.archivo_chat),
            joinedload(models.Postulacion.bloqueo_chat),
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
def _conversacion_out(
    p: models.Postulacion, usuario: models.Usuario, no_leidos: int = 0, ultimo: Optional[models.Mensaje] = None
) -> ConversacionOut:
    otra = _otra_parte(p, usuario)
    detenida = p.cierre_moderacion is not None
    archivada = _archivada(p)
    bloqueada = _bloqueada(p)
    return ConversacionOut(
        archivada=archivada,
        archivada_por_mi=archivada and p.archivo_chat.archivada_por == usuario.id,
        bloqueada=bloqueada,
        bloqueada_por_mi=bloqueada and p.bloqueo_chat.bloqueado_por == usuario.id,
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


def _mensajes_inapropiados(db: Session, p: models.Postulacion, usuario: models.Usuario) -> List[MensajeInapropiadoOut]:
    """
    Si la moderación detuvo este chat porque la otra persona fue sancionada, quien no fue
    sancionado puede leer (si quiere) los mensajes bloqueados que nunca le llegaron.
    """
    if p.cierre_moderacion is None:
        return []
    A = models.Advertencia
    filas = (
        db.query(A)
        .filter(A.postulacion_id == p.id, A.usuario_id != usuario.id, A.cuenta.is_(True))
        .order_by(A.fecha, A.id)
        .all()
    )
    return [MensajeInapropiadoOut(id=a.id, contenido=a.contenido, categoria=a.categoria, fecha=a.fecha) for a in filas]


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
        # Una conversación cerrada y sin mensajes solo se muestra si tiene un aviso que dar
        # (detenida por moderación, archivada o bloqueada) y su historial sigue vigente.
        con_aviso = p.cierre_moderacion is not None or _archivada(p) or _bloqueada(p)
        if not _puede_escribir(p) and p.id not in ultimos and not (con_aviso and _historial_vigente(p)):
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
    """
    El portal llama a este endpoint cada pocos segundos mientras la conversación está abierta,
    así que está pensado para hacer pocas consultas: arma toda la respuesta dentro de la misma
    transacción y solo hace commit si algo cambió (un commit "expira" los objetos cargados y
    obligaría a volver a consultarlos uno por uno).
    """
    p = _visible(db, postulacion_id, usuario)
    _borrar_vencidos(db, [p])

    # Abrir el hilo = leer lo que escribió la otra persona.
    marcados = db.query(models.Mensaje).filter(
        models.Mensaje.postulacion_id == p.id,
        models.Mensaje.autor_id != usuario.id,
        models.Mensaje.leido_en.is_(None),
    ).update({"leido_en": ahora()}, synchronize_session=False)
    aviso = sanciones.aviso_para_receptor(db, p.id, usuario.id)

    recientes = (
        db.query(models.Mensaje)
        .filter(models.Mensaje.postulacion_id == p.id)
        .order_by(models.Mensaje.id.desc())
        .limit(MAX_MENSAJES_HILO)
        .all()
    )
    recientes.reverse()  # del más antiguo al más nuevo
    # Como el tope (500) es mucho mayor que el mínimo para reportar (3), contar los mensajes
    # cargados equivale a contarlos todos: nos ahorramos un COUNT.
    puede_reportar = (
        len(recientes) >= sanciones.MIN_MENSAJES_REPORTAR
        and not sanciones.tiene_reporte_pendiente(db, p.id, usuario.id)
    )
    salida = HiloOut(
        conversacion=_conversacion_out(p, usuario, 0, recientes[-1] if recientes else None),
        mensajes=[_mensaje_out(m, usuario) for m in recientes],
        mensajes_inapropiados=_mensajes_inapropiados(db, p, usuario),
        puede_reportar=puede_reportar,
        aviso_moderacion=aviso,
    )
    if marcados or aviso:
        db.commit()
    return salida


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
        motivo = "bloqueada" if _bloqueada(p) else "archivada" if _archivada(p) else "cerrada"
        raise HTTPException(status_code=409, detail=f"Esta conversación está {motivo}: ya no admite mensajes")
    texto = datos.contenido.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Escribe un mensaje")

    # Moderación: el mensaje bloqueado no se guarda como mensaje, así nunca le llega a la otra persona.
    # Los mensajes anteriores (contexto para la IA) solo se consultan si el texto irá a la IA.
    contexto: List[str] = []
    if moderacion.requiere_ia(texto):
        previos = (
            db.query(models.Mensaje.contenido)
            .filter(models.Mensaje.postulacion_id == p.id)
            .order_by(models.Mensaje.id.desc())
            .limit(moderacion.CONTEXTO_MENSAJES)
            .all()
        )
        contexto = [c for (c,) in reversed(previos)]
    resultado = moderacion.moderar(texto, contexto)
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
    db.flush()  # asigna el id; la respuesta se arma antes del commit para no tener que recargar el mensaje
    salida = _mensaje_out(mensaje, usuario)
    db.commit()
    return salida


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
    reporte = sanciones.crear_reporte(
        db, postulacion=p, reportado=_otra_parte(p, usuario), reportante=usuario, origen="usuario", motivo=datos.motivo.strip()
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
    """Cierra el chat para las dos personas (solo lectura). La postulación no cambia."""
    p = _visible(db, postulacion_id, usuario)
    if _archivada(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está archivada")
    if not _en_curso(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está cerrada")
    p.archivo_chat = models.ConversacionArchivada(archivada_por=usuario.id, fecha=ahora())
    sanciones.avisar(db, _otra_parte(p, usuario).id, (
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
    sanciones.avisar(db, _otra_parte(p, usuario).id, f"«{p.solicitud.titulo}»: la otra persona reabrió la conversación. Ya puedes escribir de nuevo.")
    db.commit()
    db.refresh(p)
    return _conversacion_out(p, usuario)


@router.post("/{postulacion_id}/bloquear", response_model=ConversacionOut)
def bloquear(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    """Bloquea a la otra persona en este chat: nadie puede escribir y solo quien bloqueó puede deshacerlo."""
    p = _visible(db, postulacion_id, usuario)
    if _bloqueada(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está bloqueada")
    if not _en_curso(p):
        raise HTTPException(status_code=409, detail="Esta conversación ya está cerrada")
    p.bloqueo_chat = models.BloqueoChat(bloqueado_por=usuario.id, fecha=ahora())
    sanciones.avisar(db, _otra_parte(p, usuario).id, (
        f"«{p.solicitud.titulo}»: la otra persona bloqueó la conversación, así que ya no se pueden "
        "enviar mensajes."
    ))
    db.commit()
    db.refresh(p)
    return _conversacion_out(p, usuario)


@router.post("/{postulacion_id}/desbloquear", response_model=ConversacionOut)
def desbloquear(
    postulacion_id: int,
    usuario: models.Usuario = Depends(ambos_roles),
    db: Session = Depends(get_db),
):
    """Quita el bloqueo. Solo puede hacerlo quien bloqueó."""
    p = _visible(db, postulacion_id, usuario)
    if not _bloqueada(p):
        raise HTTPException(status_code=409, detail="Esta conversación no está bloqueada")
    if p.bloqueo_chat.bloqueado_por != usuario.id:
        raise HTTPException(status_code=403, detail="Solo quien bloqueó la conversación puede desbloquearla")
    p.bloqueo_chat = None
    sanciones.avisar(db, _otra_parte(p, usuario).id, f"«{p.solicitud.titulo}»: la otra persona desbloqueó la conversación. Ya puedes escribir de nuevo.")
    db.commit()
    db.refresh(p)
    return _conversacion_out(p, usuario)
