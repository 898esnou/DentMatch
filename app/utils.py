"""Funciones pequeñas compartidas por los routers."""
from typing import Optional, Type, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

T = TypeVar("T")


def nombre_corto(nombre_completo: str) -> str:
    """
    'Matías Rojas Valenzuela' -> 'Matías Rojas V.'
    Es lo único que ve la otra parte: nunca se muestra el nombre completo.
    """
    partes = nombre_completo.split()
    if len(partes) >= 3:
        return f"{partes[0]} {partes[-2]} {partes[-1][0]}."
    return " ".join(partes)


def obtener_o_404(db: Session, modelo: Type[T], id_: int, detalle: Optional[str] = None) -> T:
    objeto = db.get(modelo, id_)
    if objeto is None:
        raise HTTPException(status_code=404, detail=detalle or "No encontrado")
    return objeto
