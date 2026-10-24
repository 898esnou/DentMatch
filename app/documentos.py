"""
Validación del documento de identidad con el que se registra una persona.

Dos tipos:
- "rut":        RUT chileno. Se valida el dígito verificador (algoritmo módulo 11).
- "extranjero": pasaporte u otro documento extranjero. No existe un dígito
                verificador común, así que solo se valida el formato.

Importante: validar el RUT solo comprueba que el número está bien formado, no
que la persona sea quien dice ser. Para estudiantes la identidad real se
comprueba con el certificado de alumno regular (ver app/routers/verificacion.py).

Todas las funciones lanzan ValueError con un mensaje listo para mostrar al usuario.
"""
import re
from typing import List

TIPOS_DOCUMENTO = ("rut", "extranjero")

PREFIJO_EXTRANJERO = "EXT-"   # distingue un documento extranjero de un RUT en la columna `rut`
LARGO_MIN_EXTRANJERO = 5
LARGO_MAX_EXTRANJERO = 16     # la columna `rut` mide 20: 4 del prefijo + 16


def _calcular_dv(cuerpo: str) -> str:
    """Dígito verificador de un RUT (módulo 11). `cuerpo` son solo los dígitos."""
    suma, multiplicador = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


# Desde 50.000.000 los RUT son de personas jurídicas (empresas), no de personas.
RUT_MINIMO_EMPRESA = 50_000_000


def normalizar_rut(texto: str) -> str:
    """
    '12.345.678-5' / '12345678-5' / '123456785' -> '12345678-5'
    Lanza ValueError si el formato es inválido o el dígito verificador no coincide.
    """
    limpio = re.sub(r"[.\s-]", "", (texto or "")).upper()
    if not re.fullmatch(r"\d{7,8}[0-9K]", limpio):
        raise ValueError("El RUT no tiene un formato válido (ejemplo: 12345678-5)")
    cuerpo, dv = limpio[:-1], limpio[-1]
    if _calcular_dv(cuerpo) != dv:
        raise ValueError("El RUT no es válido: el dígito verificador no coincide")
    if int(cuerpo) >= RUT_MINIMO_EMPRESA:
        raise ValueError("Ese RUT corresponde a una empresa: ingresa el RUT personal de una persona natural")
    return f"{cuerpo}-{dv}"


def normalizar_documento_extranjero(texto: str) -> str:
    """'ab-123 456' -> 'EXT-AB123456' (solo letras y números, 5 a 16 caracteres)."""
    limpio = re.sub(r"[\s-]", "", (texto or "")).upper()
    if not re.fullmatch(r"[A-Z0-9]+", limpio):
        raise ValueError("El documento extranjero solo puede tener letras y números")
    if not LARGO_MIN_EXTRANJERO <= len(limpio) <= LARGO_MAX_EXTRANJERO:
        raise ValueError(
            f"El documento extranjero debe tener entre {LARGO_MIN_EXTRANJERO} y {LARGO_MAX_EXTRANJERO} caracteres"
        )
    return f"{PREFIJO_EXTRANJERO}{limpio}"


def normalizar_documento(tipo: str, texto: str) -> str:
    """Devuelve el documento en su forma canónica, lista para guardar en `usuarios.rut`."""
    if tipo == "rut":
        return normalizar_rut(texto)
    if tipo == "extranjero":
        return normalizar_documento_extranjero(texto)
    raise ValueError("Tipo de documento inválido")


def variantes_guardadas(documento: str) -> List[str]:
    """
    Formas en que ese mismo documento pudo haberse guardado antes (los registros
    antiguos pueden tener puntos: '12.345.678-5'). Sirve para detectar duplicados.
    """
    if documento.startswith(PREFIJO_EXTRANJERO):
        return [documento]
    cuerpo, dv = documento.split("-")
    con_puntos = f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
    return [documento, con_puntos]
