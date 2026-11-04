"""
Construye el caché de embeddings del catálogo (app/datos/embeddings_cache.npz).

El caché guarda los vectores de todas las frases de app/datos/procedimientos.json. Mientras el
JSON no cambie, la búsqueda lo reutiliza y NO llama a la API de Gemini para el catálogo.

Conviene ejecutarlo cada vez que se edite el JSON, y subir el .npz resultante al repositorio:
así el servidor desplegado (donde no se puede esperar varios minutos en la primera consulta)
parte con el índice ya construido.

La capa gratuita de Gemini permite 100 solicitudes por minuto y cada frase cuenta como una,
así que con catálogos grandes el script espera entre tandas (ver PAUSA_ENTRE_LOTES).

Uso (desde la raíz del proyecto):
    python -m scripts.construir_cache            # solo si el caché está desactualizado
    python -m scripts.construir_cache --forzar   # lo reconstruye aunque esté al día
"""
import sys

import numpy as np
from dotenv import load_dotenv

# Este script corre aparte de la app, así que carga el .env él mismo.
load_dotenv(override=True)

from app import busqueda_semantica as bs  # noqa: E402 (debe ir después de load_dotenv)


def cache_al_dia(hash_actual: str) -> bool:
    if not bs.RUTA_CACHE.exists():
        return False
    return str(np.load(bs.RUTA_CACHE)["hash"]) == hash_actual


def main() -> None:
    catalogo, hash_actual = bs.cargar_catalogo()
    total_frases = sum(len(p["frases"]) for p in catalogo)

    if "--forzar" not in sys.argv and cache_al_dia(hash_actual):
        print(f"El caché ya está al día ({total_frases} frases). Nada que hacer.")
        return

    if bs.RUTA_CACHE.exists():
        bs.RUTA_CACHE.unlink()
    tandas = -(-total_frases // bs.TAMANO_LOTE)
    espera = (tandas - 1) * bs.PAUSA_ENTRE_LOTES
    print(f"{total_frases} frases en {tandas} tanda(s). Esperas por el límite de la API: unos {espera} segundos.")

    vectores, _, _ = bs.construir_indice()
    print(f"Listo: {vectores.shape[0]} vectores guardados en {bs.RUTA_CACHE}")
    print("Recuerda subir este archivo al repositorio junto con el cambio del JSON.")


if __name__ == "__main__":
    main()
