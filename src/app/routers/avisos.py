"""
Avisos para el usuario (ej. "tu postulación fue cancelada").
- GET /api/avisos   devuelve los que aún no vio y los marca como vistos
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.auth import require_rol
from app.database import get_db
from app.schemas_dominio import AvisoOut
from app.servicios import ahora

router = APIRouter(prefix="/api/avisos", tags=["avisos"])


@router.get("", response_model=List[AvisoOut])
def avisos_nuevos(
    usuario: models.Usuario = Depends(require_rol("estudiante", "paciente")),
    db: Session = Depends(get_db),
):
    A = models.AvisoUsuario
    nuevos = db.query(A).filter(A.usuario_id == usuario.id, A.leido_en.is_(None)).order_by(A.id).all()
    salida = [AvisoOut(id=a.id, texto=a.texto, fecha=a.fecha) for a in nuevos]
    for a in nuevos:
        a.leido_en = ahora()
    db.commit()
    return salida
