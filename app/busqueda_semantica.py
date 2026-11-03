"""
Búsqueda semántica de procedimientos odontológicos para DentMatch.

Idea general:
  1. Cada frase del catálogo (casual o profesional) se convierte en un vector (embedding).
  2. Esos vectores se guardan en un caché en disco (se calculan una sola vez).
  3. En cada búsqueda solo se convierte el texto del usuario en vector y se
     compara contra los del catálogo (similitud coseno).

IMPORTANTE: este módulo NO diagnostica ni recomienda tratamientos.
Solo relaciona lo que escribe la persona con procedimientos del catálogo.

Configuración: la variable GEMINI_API_KEY la carga database.py (load_dotenv)
al arrancar la app. Si usas este módulo en un script aparte, llama a
load_dotenv() antes (ver scripts/evaluar.py).
"""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from google import genai
from google.genai import errors, types

from .catalogos import AREAS

# --- Configuración ---------------------------------------------------------
MODELO = "gemini-embedding-001"
CARPETA_DATOS = Path(__file__).parent / "datos"   # independiente de dónde se ejecute Python
RUTA_JSON = CARPETA_DATOS / "procedimientos.json"
RUTA_CACHE = os.path.join(tempfile.gettempdir(), "embeddings_cache.npz")
TAMANO_LOTE = 50           # frases enviadas por llamada a la API
MAX_REINTENTOS = 3         # intentos ante errores temporales
CODIGOS_TEMPORALES = {429, 500, 502, 503, 504}  # cuota agotada o servidor ocupado
UMBRAL_POR_DEFECTO = 0.5   # valor inicial: se calibra con scripts/evaluar.py

# Niveles de "coincidencia" que se muestran al paciente. NO son probabilidades de
# acierto: indican qué tan parecido es el texto escrito al procedimiento del catálogo.
# PROVISORIOS: ajustar mirando los puntajes de scripts/evaluar.py con consultas reales.
NIVEL_ALTO = 0.82
NIVEL_MEDIO = 0.76

_client = None  # se crea la primera vez que se necesita (ya con el .env cargado)


def _obtener_cliente() -> genai.Client:
    """Crea el cliente de Gemini una sola vez (lee GEMINI_API_KEY del entorno)."""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


class BuscadorNoDisponible(RuntimeError):
    """La API de embeddings no respondió o falta configurar la clave.

    El router la convierte en un 503 con un mensaje genérico para el usuario.
    """


def _llamar_api_con_reintentos(lote: list[str], tipo_tarea: str) -> list[list[float]]:
    """Llama a la API. Reintenta solo errores temporales (cuota, servidor, red).

    Un error definitivo (clave inválida, petición mala) falla de inmediato:
    reintentarlo solo haría esperar al usuario sin cambiar el resultado.
    """
    try:
        cliente = _obtener_cliente()
    except ValueError as error:  # típicamente: falta GEMINI_API_KEY
        raise BuscadorNoDisponible(f"Configuración de Gemini inválida: {error}") from error

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            respuesta = cliente.models.embed_content(
                model=MODELO,
                contents=lote,
                config=types.EmbedContentConfig(task_type=tipo_tarea),
            )
            return [embedding.values for embedding in respuesta.embeddings]
        except Exception as error:  # el SDK y la red lanzan distintos tipos
            es_definitivo = (
                isinstance(error, errors.APIError) and error.code not in CODIGOS_TEMPORALES
            )
            if es_definitivo or intento == MAX_REINTENTOS:
                raise BuscadorNoDisponible(f"Falló la API de embeddings: {error}") from error
            time.sleep(2**intento)  # espera 2 s, luego 4 s


def embeber(textos: list[str], tipo_tarea: str) -> np.ndarray:
    """Convierte textos en vectores normalizados (largo 1).

    tipo_tarea:
      - "RETRIEVAL_DOCUMENT" para frases del catálogo.
      - "RETRIEVAL_QUERY" para lo que escribe el usuario.
    Al normalizar, el producto punto equivale a la similitud coseno.
    """
    vectores = []
    for inicio in range(0, len(textos), TAMANO_LOTE):
        lote = textos[inicio : inicio + TAMANO_LOTE]
        vectores.extend(_llamar_api_con_reintentos(lote, tipo_tarea))

    matriz = np.array(vectores, dtype=np.float32)
    return matriz / np.linalg.norm(matriz, axis=1, keepdims=True)


def validar_catalogo(catalogo: list[dict]) -> None:
    """Falla de inmediato si el JSON tiene errores (mejor que fallar en silencio)."""
    ids_vistos = set()
    for procedimiento in catalogo:
        id_procedimiento = procedimiento["id"]
        if id_procedimiento in ids_vistos:
            raise ValueError(f"Id repetido en procedimientos.json: '{id_procedimiento}'")
        ids_vistos.add(id_procedimiento)

        if procedimiento["area"] not in AREAS:
            raise ValueError(
                f"Área inválida '{procedimiento['area']}' en '{id_procedimiento}'. "
                f"Válidas (catalogos.py): {list(AREAS)}"
            )
        if not procedimiento["frases"]:
            raise ValueError(f"'{id_procedimiento}' no tiene frases")


def cargar_catalogo() -> tuple[list[dict], str]:
    """Lee y valida el JSON. Devuelve (procedimientos, hash de su contenido)."""
    contenido = RUTA_JSON.read_text(encoding="utf-8")
    catalogo = json.loads(contenido)
    validar_catalogo(catalogo)
    return catalogo, hashlib.sha256(contenido.encode()).hexdigest()


def construir_indice() -> tuple[np.ndarray, list[str], dict[str, dict]]:
    """Devuelve (matriz de vectores, id de procedimiento por fila, datos por id).

    Si el JSON no cambió desde la última vez, usa el caché y NO llama a la API.
    """
    catalogo, hash_actual = cargar_catalogo()
    datos_por_id = {procedimiento["id"]: procedimiento for procedimiento in catalogo}

    if RUTA_CACHE.exists():
        cache = np.load(RUTA_CACHE)
        if str(cache["hash"]) == hash_actual:
            return cache["vectores"], cache["ids"].tolist(), datos_por_id

    frases, ids = [], []
    for procedimiento in catalogo:
        for frase in procedimiento["frases"]:
            frases.append(frase)
            ids.append(procedimiento["id"])

    vectores = embeber(frases, "RETRIEVAL_DOCUMENT")
    np.savez(RUTA_CACHE, vectores=vectores, ids=np.array(ids), hash=hash_actual)
    return vectores, ids, datos_por_id


def ordenar_por_procedimiento(
    puntajes: np.ndarray, ids: list[str], top_k: int, umbral: float
) -> list[tuple[str, float]]:
    """Agrupa puntajes por procedimiento (gana su frase más parecida) y ordena.

    Está separada de buscar() para poder probarla sin llamar a la API.
    """
    mejor_por_procedimiento: dict[str, float] = {}
    for id_procedimiento, puntaje in zip(ids, puntajes):
        actual = mejor_por_procedimiento.get(id_procedimiento, 0.0)
        mejor_por_procedimiento[id_procedimiento] = max(actual, float(puntaje))

    ranking = sorted(mejor_por_procedimiento.items(), key=lambda par: par[1], reverse=True)
    return [(id_proc, puntaje) for id_proc, puntaje in ranking[:top_k] if puntaje >= umbral]


def nivel_coincidencia(puntaje: float) -> str:
    """Traduce un puntaje de similitud a 'alta', 'media' o 'baja'.

    Se muestra la etiqueta y no el número: un 0.81 de similitud no es un "81 % de
    seguridad", y un porcentaje daría una precisión que el modelo no tiene.
    """
    if puntaje >= NIVEL_ALTO:
        return "alta"
    if puntaje >= NIVEL_MEDIO:
        return "media"
    return "baja"


def buscar(consulta: str, top_k: int = 3, umbral: float = UMBRAL_POR_DEFECTO) -> list[dict]:
    """Devuelve los procedimientos del catálogo más parecidos a la consulta.

    Cada resultado: {"id", "nombre", "area", "puntaje", "coincidencia"}.
    Devuelve lista vacía si ninguno supera el umbral (consulta no relacionada).
    No envíes datos personales en la consulta (nombre, RUT, teléfono).
    """
    consulta = consulta.strip()
    if not consulta:
        return []

    vectores, ids, datos_por_id = construir_indice()
    vector_consulta = embeber([consulta], "RETRIEVAL_QUERY")[0]
    puntajes = vectores @ vector_consulta  # similitud coseno con cada frase

    resultados = []
    for id_procedimiento, puntaje in ordenar_por_procedimiento(puntajes, ids, top_k, umbral):
        datos = datos_por_id[id_procedimiento]
        resultados.append(
            {
                "id": id_procedimiento,
                "nombre": datos["nombre_profesional"],
                "area": datos["area"],
                "puntaje": round(puntaje, 3),
                "coincidencia": nivel_coincidencia(puntaje),
            }
        )
    return resultados
