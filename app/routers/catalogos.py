"""
GET /api/catalogos -> áreas clínicas, días y estados (para llenar selects y filtros).
Público: no contiene datos de usuarios.
"""
from fastapi import APIRouter

from app import catalogos

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])


@router.get("")
def obtener_catalogos():
    return {
        "areas": [{"clave": k, "nombre": v} for k, v in catalogos.AREAS.items()],
        "dias_semana": list(catalogos.DIAS_SEMANA),
        "estados_requerimiento": list(catalogos.ESTADOS_REQUERIMIENTO),
        "estados_solicitud": list(catalogos.ESTADOS_SOLICITUD),
        "estados_postulacion": list(catalogos.ESTADOS_POSTULACION),
        "estados_cita": list(catalogos.ESTADOS_CITA),
    }
