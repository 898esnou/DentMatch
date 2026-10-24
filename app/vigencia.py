"""
Vigencia SEMESTRAL de la verificación del estudiante.

Lo que cuenta es el MES Y AÑO de emisión del certificado (el día da lo mismo):
- emitido de enero a junio       -> vale hasta el 30 de junio de ese año
- emitido de julio a diciembre   -> vale hasta el 31 de diciembre de ese año
Después del fin de semestre hay GRACIA_DIAS días para renovarlo manteniendo el
acceso (el estudiante recibe un aviso); pasado ese plazo vuelve a 'No verificado'.

El vencimiento se aplica al consultar (vencer_caducadas), sin tareas programadas.
"""
from datetime import date, timedelta
from typing import Dict, NamedTuple, Optional

from sqlalchemy.orm import Session

from app import models
from app.servicios import ahora

GRACIA_DIAS = 7


class Vigencia(NamedTuple):
    vence_el: date          # último día del semestre del certificado
    gracia_hasta: date      # último día con acceso, ya vencido el semestre

    def en_gracia(self, hoy: date) -> bool:
        return self.vence_el < hoy <= self.gracia_hasta

    def caducada(self, hoy: date) -> bool:
        return hoy > self.gracia_hasta


def fin_de_semestre(emision: date) -> date:
    return date(emision.year, 6, 30) if emision.month <= 6 else date(emision.year, 12, 31)


def calcular(emision: date) -> Vigencia:
    fin = fin_de_semestre(emision)
    return Vigencia(fin, fin + timedelta(days=GRACIA_DIAS))


def _fecha_base(certificado: models.VerificacionEstudiante) -> date:
    # Si no se conoce la emisión (aprobación manual), se usa cuándo se subió.
    if certificado.fecha_emision:
        return certificado.fecha_emision
    return (certificado.fecha_subida or ahora()).date()


def ultima_aprobada(db: Session, estudiante_id: int) -> Optional[models.VerificacionEstudiante]:
    V = models.VerificacionEstudiante
    return (
        db.query(V).filter(V.estudiante_id == estudiante_id, V.estado == "Aprobada")
        .order_by(V.id.desc()).first()
    )


def vigencia_de(db: Session, estudiante_id: int) -> Optional[Vigencia]:
    cert = ultima_aprobada(db, estudiante_id)
    return calcular(_fecha_base(cert)) if cert else None


def vencer_caducadas(db: Session, hoy: Optional[date] = None) -> int:
    """Pasa a 'No verificado' a los Activo cuya gracia terminó. Devuelve cuántos."""
    hoy = hoy or ahora().date()
    P, V = models.PerfilEstudiante, models.VerificacionEstudiante
    activos = [p.usuario_id for p in db.query(P).filter(P.estado_verificacion == "Activo")]
    if not activos:
        return 0
    ultimas: Dict[int, models.VerificacionEstudiante] = {}
    for c in db.query(V).filter(V.estudiante_id.in_(activos), V.estado == "Aprobada").order_by(V.id):
        ultimas[c.estudiante_id] = c  # el último (id mayor) gana
    vencidos = [uid for uid, c in ultimas.items() if calcular(_fecha_base(c)).caducada(hoy)]
    if vencidos:
        db.query(P).filter(P.usuario_id.in_(vencidos)).update(
            {P.estado_verificacion: "No verificado"}, synchronize_session=False
        )
        db.commit()
    return len(vencidos)
