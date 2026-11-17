"""
Advertencias, baneos, reportes y avisos de la moderación del chat (Épica 5).

Reglas:
- Un mensaje bloqueado por insulto o acoso es una advertencia; las advertencias valen
  DIAS_ADVERTENCIAS días. Al llegar a MAX_ADVERTENCIAS la cuenta queda baneada y se crea un
  reporte automático para el administrador. Los mensajes "fuera de tema" solo avisan.
- Al banear, las postulaciones de esa persona se cancelan y a quienes tenían un
  vínculo con ella se les deja un aviso (sin contarles el motivo).
- Las funciones NO hacen commit: lo hace quien las llama (así todo queda en una transacción).
"""
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.moderacion import AVISO_AL_RECEPTOR, Resultado
from app.servicios import ahora, recalcular_estado_solicitud
from app.utils import nombre_corto

MAX_ADVERTENCIAS = 3
DIAS_ADVERTENCIAS = 30        # cuánto tiempo cuenta una advertencia
MIN_MENSAJES_REPORTAR = 3     # mensajes en la conversación para habilitar "Reportar"
MAX_EVIDENCIA = 20            # mensajes que se copian como evidencia de un reporte
DIAS_MAX_SUSPENSION = 90      # tope del time-out que puede dar un administrador

# Lo que ve la persona que NO fue sancionada cuando el chat se detiene (no se nombra a nadie).
CIERRE_PARA_PACIENTE = (
    "Este chat ha sido detenido por incumplimiento de las normas de convivencia de nuestra "
    "plataforma. Te sugerimos buscar otro estudiante que pueda estar interesado en tratarte. "
    "Lamentamos el inconveniente."
)
CIERRE_PARA_ESTUDIANTE = (
    "Este chat ha sido detenido por incumplimiento de las normas de convivencia de nuestra "
    "plataforma. Te sugerimos buscar otro caso que necesite tu atención. "
    "Lamentamos el inconveniente."
)


def mensaje_de_cierre(rol_de_quien_lee: str) -> str:
    return CIERRE_PARA_PACIENTE if rol_de_quien_lee == "paciente" else CIERRE_PARA_ESTUDIANTE


MENSAJE_BANEO = (
    "Tu cuenta fue suspendida por incumplir las normas de convivencia de DentMatch. "
    "Un administrador revisará el caso."
)


# ---------------------------------------------------------------- estado de la cuenta
def verificar_cuenta(db: Session, usuario: models.Usuario) -> None:
    """Corta el acceso (403) a quien está baneado o en time-out. Los admin nunca se bloquean."""
    if usuario.rol == "admin":
        return
    fila = db.get(models.EstadoCuenta, usuario.id)
    if fila is None or fila.estado == "activo":
        return
    if fila.estado == "suspendido":
        if fila.suspendido_hasta is not None and fila.suspendido_hasta <= ahora():
            fila.estado, fila.suspendido_hasta, fila.motivo = "activo", None, None  # terminó el time-out
            db.commit()
            return
        hasta = fila.suspendido_hasta.strftime("%d/%m/%Y") if fila.suspendido_hasta else "nuevo aviso"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=fila.motivo or f"Tu cuenta está suspendida hasta el {hasta} por incumplir las normas de convivencia.",
        )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=fila.motivo or MENSAJE_BANEO)


def cuenta_activa(db: Session, usuario_id: int) -> bool:
    fila = db.get(models.EstadoCuenta, usuario_id)
    return fila is None or fila.estado == "activo"


# ---------------------------------------------------------------- avisos
def avisar(db: Session, usuario_id: int, texto: str) -> None:
    db.add(models.AvisoUsuario(usuario_id=usuario_id, texto=texto, fecha=ahora()))


# ---------------------------------------------------------------- advertencias
def contar_advertencias_varios(db: Session, usuario_ids) -> dict:
    """Advertencias vigentes de varias cuentas en una sola consulta: {usuario_id: cantidad}."""
    ids = list(usuario_ids)
    if not ids:
        return {}
    desde = ahora() - timedelta(days=DIAS_ADVERTENCIAS)
    filas = (
        db.query(models.Advertencia.usuario_id, func.count(models.Advertencia.id))
        .filter(
            models.Advertencia.usuario_id.in_(ids),
            models.Advertencia.cuenta.is_(True),
            models.Advertencia.fecha >= desde,
        )
        .group_by(models.Advertencia.usuario_id)
        .all()
    )
    return dict(filas)


def contar_advertencias(db: Session, usuario_id: int) -> int:
    desde = ahora() - timedelta(days=DIAS_ADVERTENCIAS)
    return (
        db.query(models.Advertencia)
        .filter(
            models.Advertencia.usuario_id == usuario_id,
            models.Advertencia.cuenta.is_(True),
            models.Advertencia.fecha >= desde,
        )
        .count()
    )


@dataclass
class Bloqueo:
    numero: Optional[int]   # advertencia N de 3 (None si el mensaje solo avisó, sin sumar)
    baneado: bool


def registrar_bloqueo(
    db: Session, usuario: models.Usuario, postulacion: models.Postulacion, resultado: Resultado, texto: str
) -> Bloqueo:
    """Guarda el mensaje bloqueado como advertencia y, si ya son 3, banea y reporta."""
    db.add(models.Advertencia(
        usuario_id=usuario.id,
        postulacion_id=postulacion.id,
        categoria=resultado.categoria,
        fuente=resultado.fuente,
        contenido=texto,
        cuenta=resultado.cuenta_como_advertencia,
        # Solo si es una falta real se le recuerda al receptor que puede reportar.
        receptor_avisado=not resultado.cuenta_como_advertencia,
        fecha=ahora(),
    ))
    db.flush()
    if not resultado.cuenta_como_advertencia:
        return Bloqueo(numero=None, baneado=False)

    numero = contar_advertencias(db, usuario.id)
    if numero < MAX_ADVERTENCIAS:
        return Bloqueo(numero=numero, baneado=False)

    aplicar_baneo(db, usuario)
    crear_reporte(
        db, postulacion=postulacion, reportado=usuario, reportante=None, origen="automatico",
        motivo=f"Llegó a {MAX_ADVERTENCIAS} advertencias en {DIAS_ADVERTENCIAS} días.",
    )
    return Bloqueo(numero=numero, baneado=True)


# ---------------------------------------------------------------- baneo y sus efectos
def aplicar_baneo(db: Session, usuario: models.Usuario) -> None:
    """Banea la cuenta (sin fecha de término) y la saca de circulación."""
    _retirar_de_circulacion(db, usuario, "baneado", None, MENSAJE_BANEO)


def aplicar_suspension(db: Session, usuario: models.Usuario, dias: int, mensaje: Optional[str] = None) -> None:
    """Time-out: igual que el baneo, pero la cuenta vuelve sola pasados `dias` días."""
    hasta = ahora() + timedelta(days=dias)
    texto = f"Tu cuenta está suspendida hasta el {hasta:%d/%m/%Y} por incumplir las normas de convivencia."
    if mensaje and mensaje.strip():
        texto += f" Mensaje del equipo: {mensaje.strip()}"
    _retirar_de_circulacion(db, usuario, "suspendido", hasta, texto)


def _retirar_de_circulacion(
    db: Session, usuario: models.Usuario, estado: str, hasta, motivo: str
) -> None:
    """
    Deja la cuenta baneada o suspendida y la saca de circulación: cancela sus postulaciones,
    cierra las solicitudes del paciente y avisa a quienes tenían un vínculo con esta persona.
    """
    fila = db.get(models.EstadoCuenta, usuario.id)
    if fila is None:
        fila = models.EstadoCuenta(usuario_id=usuario.id)
        db.add(fila)
    fila.estado, fila.suspendido_hasta, fila.motivo, fila.actualizado_en = estado, hasta, motivo, ahora()

    P, S = models.Postulacion, models.Solicitud
    consulta = db.query(P).join(S, P.solicitud_id == S.id).filter(P.estado.in_(("Pendiente", "Aceptada")))
    if usuario.rol == "estudiante":
        consulta = consulta.filter(P.estudiante_id == usuario.id)
    else:
        consulta = consulta.filter(S.paciente_id == usuario.id)

    for p in consulta.all():
        solicitud = p.solicitud
        if solicitud.estado_api == "Completada":
            continue  # un tratamiento ya terminado no se toca
        tenia_chat = p.estado == "Aceptada"
        p.estado, p.fecha_respuesta = "Cancelada", ahora()
        contraparte_id = solicitud.paciente_id if usuario.rol == "estudiante" else p.estudiante_id
        contraparte_rol = "paciente" if usuario.rol == "estudiante" else "estudiante"
        if tenia_chat:
            # El chat queda cerrado con una explicación visible para la persona no involucrada.
            if p.cierre_moderacion is None:
                p.cierre_moderacion = models.CierreModeracion(fecha=ahora())
            avisar(db, contraparte_id, f"«{solicitud.titulo}»: {mensaje_de_cierre(contraparte_rol)}")
        elif usuario.rol == "estudiante":
            avisar(db, contraparte_id, (
                f"{nombre_corto(usuario.nombre_completo)} ya no está disponible en la plataforma: su "
                f"postulación a «{solicitud.titulo}» fue cancelada. Puedes buscar otro estudiante."
            ))
        else:
            avisar(db, contraparte_id, (
                f"El caso «{solicitud.titulo}» ya no está disponible: tu postulación fue cancelada."
            ))

    db.flush()
    if usuario.rol == "paciente":
        for solicitud in db.query(S).filter(S.paciente_id == usuario.id, S.estado.in_(("Buscando", "Asignado"))):
            if solicitud.detalle is None or solicitud.detalle.completada_en is None:
                solicitud.estado = "Cancelado"
    else:
        # Las solicitudes que tenían a este estudiante aceptado vuelven a estar abiertas.
        for p in db.query(P).filter(P.estudiante_id == usuario.id, P.estado == "Cancelada"):
            recalcular_estado_solicitud(p.solicitud)


# ---------------------------------------------------------------- reportes
def _evidencia(db: Session, postulacion: models.Postulacion, reportado_id: int) -> str:
    """Copia de lo que pasó en la conversación (el chat se borra a los 30 días de cerrado)."""
    recientes = (
        db.query(models.Mensaje)
        .filter(models.Mensaje.postulacion_id == postulacion.id)
        .order_by(models.Mensaje.id.desc())
        .limit(MAX_EVIDENCIA)
        .all()
    )
    recientes.reverse()
    bloqueados = (
        db.query(models.Advertencia)
        .filter(models.Advertencia.postulacion_id == postulacion.id, models.Advertencia.usuario_id == reportado_id)
        .order_by(models.Advertencia.id)
        .all()
    )
    return json.dumps({
        "mensajes": [
            {"autor_id": m.autor_id, "contenido": m.contenido, "fecha": m.fecha_creacion.isoformat()}
            for m in recientes
        ],
        "mensajes_bloqueados": [
            {"contenido": a.contenido, "categoria": a.categoria, "fuente": a.fuente, "fecha": a.fecha.isoformat()}
            for a in bloqueados
        ],
    }, ensure_ascii=False)


def crear_reporte(
    db: Session, *, postulacion: models.Postulacion, reportado: models.Usuario,
    reportante: Optional[models.Usuario], origen: str, motivo: str,
) -> models.Reporte:
    reporte = models.Reporte(
        postulacion_id=postulacion.id,
        reportante_id=reportante.id if reportante else None,
        reportado_id=reportado.id,
        origen=origen,
        motivo=motivo,
        evidencia=_evidencia(db, postulacion, reportado.id),
        estado="Pendiente",
        fecha_creacion=ahora(),
    )
    db.add(reporte)
    return reporte


def tiene_reporte_pendiente(db: Session, postulacion_id: int, reportante_id: int) -> bool:
    return (
        db.query(models.Reporte.id)
        .filter(
            models.Reporte.postulacion_id == postulacion_id,
            models.Reporte.reportante_id == reportante_id,
            models.Reporte.estado == "Pendiente",
        )
        .first()
        is not None
    )


def aviso_para_receptor(db: Session, postulacion_id: int, receptor_id: int) -> Optional[str]:
    """
    Si la otra persona tuvo mensajes bloqueados que el receptor aún no sabe, devuelve el
    recordatorio de "Reportar" (una sola vez) y lo marca como visto.
    """
    A = models.Advertencia
    pendientes: List[models.Advertencia] = (
        db.query(A)
        .filter(A.postulacion_id == postulacion_id, A.usuario_id != receptor_id, A.receptor_avisado.is_(False))
        .all()
    )
    if not pendientes:
        return None
    for a in pendientes:
        a.receptor_avisado = True
    return AVISO_AL_RECEPTOR


# ---------------------------------------------------------------- decisiones del administrador
def reiniciar_advertencias(db: Session, usuario_id: int) -> None:
    """Las advertencias anteriores dejan de contar (queda el registro como evidencia)."""
    db.query(models.Advertencia).filter(
        models.Advertencia.usuario_id == usuario_id, models.Advertencia.cuenta.is_(True)
    ).update({"cuenta": False}, synchronize_session=False)


def levantar_sancion(db: Session, usuario: models.Usuario) -> None:
    """
    Reactiva la cuenta. Las postulaciones y chats que se cancelaron NO se restituyen (la persona puede
    iniciar vínculos nuevos), pero se avisa a ambas partes.
    """
    fila = db.get(models.EstadoCuenta, usuario.id)
    if fila is None or fila.estado == "activo":
        return
    fila.estado, fila.suspendido_hasta, fila.motivo, fila.actualizado_en = "activo", None, None, ahora()
    reiniciar_advertencias(db, usuario.id)
    avisar(db, usuario.id, (
        "Revisamos tu caso y tu cuenta fue reactivada. Te recordamos mantener un trato respetuoso: "
        "las normas de convivencia aplican a todas las conversaciones."
    ))
    P, S = models.Postulacion, models.Solicitud
    cerradas = (
        db.query(P).join(S, P.solicitud_id == S.id)
        .filter(P.cierre_moderacion.has(), (P.estudiante_id == usuario.id) | (S.paciente_id == usuario.id))
        .all()
    )
    for p in cerradas:
        contraparte_id = p.solicitud.paciente_id if p.estudiante_id == usuario.id else p.estudiante_id
        avisar(db, contraparte_id, (
            f"«{p.solicitud.titulo}»: la otra persona fue revisada por el equipo y su cuenta se reactivó. "
            "Si aún te interesa, puedes iniciar un nuevo contacto."
        ))


class DecisionInvalida(ValueError):
    """La decisión del administrador no se puede aplicar (el router la convierte en 422/409)."""


def resolver_reporte(
    db: Session, reporte: models.Reporte, admin: models.Usuario, *,
    decision: str, dias: Optional[int] = None, mensaje: Optional[str] = None, nota: Optional[str] = None,
) -> None:
    """
    Aplica la decisión sobre un reporte pendiente:
    - baneo:      la cuenta queda baneada.
    - suspension: time-out de `dias` días con un mensaje opcional para la persona.
    - descartar:  no hubo falta. Si el reporte era automático (la cuenta estaba baneada por las
                  3 advertencias), se levanta la sanción. En uno de otra persona no cambia nada.
    """
    if reporte.estado != "Pendiente":
        raise DecisionInvalida("Este reporte ya fue resuelto")
    reportado = reporte.reportado
    if reportado.rol == "admin":
        raise DecisionInvalida("No se puede sancionar a un administrador")

    if decision == "baneo":
        aplicar_baneo(db, reportado)
    elif decision == "suspension":
        if dias is None or not 1 <= dias <= DIAS_MAX_SUSPENSION:
            raise DecisionInvalida(f"Indica cuántos días dura el time-out (de 1 a {DIAS_MAX_SUSPENSION})")
        aplicar_suspension(db, reportado, dias, mensaje)
        reiniciar_advertencias(db, reportado.id)   # vuelve con la cuenta limpia
    elif decision == "descartar":
        if reporte.origen == "automatico":
            levantar_sancion(db, reportado)
    else:
        raise DecisionInvalida("Decisión inválida")

    reporte.estado, reporte.decision = "Resuelto", decision
    reporte.suspension_dias = dias if decision == "suspension" else None
    reporte.nota_admin = (nota or "").strip() or None
    reporte.resuelto_por, reporte.fecha_resolucion = admin.id, ahora()

    if reporte.reportante_id is not None:   # quien reportó se entera de que se revisó (sin detalles)
        avisar(db, reporte.reportante_id, (
            "Revisamos tu reporte y tomamos las medidas necesarias. Gracias por ayudarnos a cuidar la comunidad."
            if decision != "descartar" else
            "Revisamos tu reporte y, por ahora, no encontramos un incumplimiento de las normas. Gracias por avisarnos."
        ))
