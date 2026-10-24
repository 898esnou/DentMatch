"""
Guarda y lee los certificados de alumno regular.

Dos destinos, según las variables de entorno:
- Supabase Storage (bucket PRIVADO "certificados"): si existen SUPABASE_URL y
  SUPABASE_SERVICE_ROLE_KEY. Es lo que se debe usar al desplegar (Vercel no
  conserva archivos locales).
- Carpeta local `uploads/certificados/`: solo para desarrollo, cuando esas
  variables no están. La carpeta está en el .gitignore.

Nunca se usa el nombre del archivo que envía el usuario: la ruta la genera el
servidor, así nadie puede escribir fuera de su carpeta ni pisar el archivo de otro.

SUPABASE_SERVICE_ROLE_KEY es una clave con acceso total: va solo en el .env y en
las variables de Vercel, nunca en el código ni en el frontend.
"""
import os
from pathlib import Path

import httpx

BUCKET = "certificados"
_TIMEOUT_SEGUNDOS = 20


class ErrorAlmacenamiento(Exception):
    """No se pudo guardar o leer el archivo."""


def _supabase():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    clave = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return (url, clave) if url and clave else None


def _carpeta_local() -> Path:
    return Path(os.getenv("UPLOADS_DIR", "uploads")) / BUCKET


def _ruta_local_segura(ruta: str) -> Path:
    base = _carpeta_local().resolve()
    destino = (base / ruta).resolve()
    if base not in destino.parents:  # defensa extra contra '../'
        raise ErrorAlmacenamiento("Ruta de archivo inválida")
    return destino


def guardar(ruta: str, contenido: bytes, tipo_contenido: str) -> None:
    config = _supabase()
    if config:
        url, clave = config
        try:
            r = httpx.post(
                f"{url}/storage/v1/object/{BUCKET}/{ruta}",
                content=contenido,
                headers={"Authorization": f"Bearer {clave}", "Content-Type": tipo_contenido},
                timeout=_TIMEOUT_SEGUNDOS,
            )
        except httpx.HTTPError as error:
            raise ErrorAlmacenamiento("No se pudo conectar con el almacenamiento") from error
        if r.status_code >= 400:
            raise ErrorAlmacenamiento(f"El almacenamiento rechazó el archivo ({r.status_code})")
        return

    destino = _ruta_local_segura(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)


def leer(ruta: str) -> bytes:
    config = _supabase()
    if config:
        url, clave = config
        try:
            r = httpx.get(
                f"{url}/storage/v1/object/authenticated/{BUCKET}/{ruta}",
                headers={"Authorization": f"Bearer {clave}"},
                timeout=_TIMEOUT_SEGUNDOS,
            )
        except httpx.HTTPError as error:
            raise ErrorAlmacenamiento("No se pudo conectar con el almacenamiento") from error
        if r.status_code >= 400:
            raise ErrorAlmacenamiento("No se encontró el archivo")
        return r.content

    destino = _ruta_local_segura(ruta)
    if not destino.is_file():
        raise ErrorAlmacenamiento("No se encontró el archivo")
    return destino.read_bytes()
