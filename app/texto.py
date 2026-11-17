"""
Utilidades de texto compartidas (sin base de datos ni dependencias externas).

Varias partes del backend comparan texto escrito por personas (comunas, disponibilidad,
moderación del chat, señales de urgencia, datos del certificado). Todas necesitan lo mismo:
ignorar tildes y mayúsculas. Antes cada módulo tenía su propia copia de esta función.
"""
import unicodedata
from typing import Optional


def quitar_tildes(texto: Optional[str]) -> str:
    """'Ñuñoa Peñalolén' -> 'Nunoa Penalolen'. No cambia mayúsculas ni minúsculas."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizar(texto: Optional[str]) -> str:
    """Minúsculas, sin tildes y sin espacios en los extremos: la forma para comparar textos."""
    return quitar_tildes((texto or "").lower()).strip()
