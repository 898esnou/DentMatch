"""Funciones pequeñas compartidas por los routers (nombres y búsquedas de texto)."""

_PARTICULAS = {"de", "del", "la", "las", "los", "y"}


def nombre_propio(texto: str) -> str:
    """'monserrat canales oportus' -> 'Monserrat Canales Oportus' (de/del/la/y en minúscula)."""
    palabras = texto.split()
    return " ".join(
        p.lower() if i > 0 and p.lower() in _PARTICULAS else p.capitalize()
        for i, p in enumerate(palabras)
    )


def nombre_corto(nombre_completo: str) -> str:
    """
    'Matías Rojas Valenzuela' -> 'Matías Rojas V.'
    Es lo único que ve la otra parte: nunca se muestra el nombre completo.
    """
    partes = nombre_propio(nombre_completo).split()
    if len(partes) >= 3:
        return f"{partes[0]} {partes[-2]} {partes[-1][0]}."
    return " ".join(partes)


ESCAPE_LIKE = "\\"


def patron_contiene(texto: str) -> str:
    """
    Patrón para `columna.ilike(patron, escape=ESCAPE_LIKE)` que busca `texto` tal cual.
    Escapa % y _ (comodines de SQL): sin esto, buscar "_" o "%" devolvería todas las filas.
    """
    limpio = texto.strip()
    for caracter in (ESCAPE_LIKE, "%", "_"):
        limpio = limpio.replace(caracter, ESCAPE_LIKE + caracter)
    return f"%{limpio}%"
