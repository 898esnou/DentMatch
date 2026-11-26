"""
Revisa el catálogo de procedimientos (app/datos/procedimientos.json) buscando frases que
puedan causar confusiones en la búsqueda semántica.

Usa los vectores ya guardados en el caché, así que NO llama a la API de Gemini ni gasta cuota.
Si el caché no existe o no corresponde al JSON actual, primero ejecuta:
    python -m scripts.construir_cache

Qué muestra:
  1. Frases de procedimientos DISTINTOS demasiado parecidas entre sí: son las que pueden hacer
     que una consulta se asigne al procedimiento equivocado. Conviene reescribirlas o quitarlas.
  2. Frases casi idénticas dentro de un mismo procedimiento: no hacen daño, pero no aportan.
  3. Qué tan cerca están los procedimientos entre sí (la frase más parecida de cada par).

Uso (desde la raíz del proyecto):
    python -m scripts.revisar_catalogo              # umbral de confusión por defecto: 0.93
    python -m scripts.revisar_catalogo --umbral 0.9
"""
import sys

import numpy as np

from app import busqueda_semantica as bs

# Con este modelo casi todas las frases odontológicas se parecen entre sí (más de 0.85),
# así que solo las similitudes muy altas indican una confusión real.
UMBRAL_CONFUSION = 0.93
UMBRAL_DUPLICADA = 0.97
MOSTRAR = 15


def leer_umbral() -> float:
    if "--umbral" in sys.argv:
        return float(sys.argv[sys.argv.index("--umbral") + 1])
    return UMBRAL_CONFUSION


def main() -> None:
    umbral = leer_umbral()
    catalogo, hash_actual = bs.cargar_catalogo()

    if not bs.RUTA_CACHE.exists():
        sys.exit("No existe el caché. Ejecuta primero: python -m scripts.construir_cache")
    cache = np.load(bs.RUTA_CACHE)
    if str(cache["hash"]) != hash_actual:
        sys.exit("El caché no corresponde al JSON actual. Ejecuta: python -m scripts.construir_cache")

    vectores = cache["vectores"]
    ids = cache["ids"].tolist()
    frases = [frase for p in catalogo for frase in p["frases"]]
    similitud = vectores @ vectores.T  # los vectores están normalizados: producto punto = coseno

    confusas, duplicadas = [], []
    mejor_entre_procedimientos: dict[tuple[str, str], tuple[float, int, int]] = {}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            s = float(similitud[i, j])
            if ids[i] != ids[j]:
                par = tuple(sorted((ids[i], ids[j])))
                if par not in mejor_entre_procedimientos or s > mejor_entre_procedimientos[par][0]:
                    mejor_entre_procedimientos[par] = (s, i, j)
                if s >= umbral:
                    confusas.append((s, i, j))
            elif s >= UMBRAL_DUPLICADA:
                duplicadas.append((s, i, j))

    print(f"Catálogo: {len(catalogo)} procedimientos, {len(frases)} frases.\n")

    print(f"1. FRASES DE PROCEDIMIENTOS DISTINTOS CON SIMILITUD >= {umbral}")
    if not confusas:
        print("   Ninguna. El catálogo no tiene frases que se confundan entre procedimientos.")
    for s, i, j in sorted(confusas, reverse=True)[:MOSTRAR]:
        print(f"   {s:.3f}  [{ids[i]}] {frases[i]!r}\n          [{ids[j]}] {frases[j]!r}")
    if len(confusas) > MOSTRAR:
        print(f"   ... y {len(confusas) - MOSTRAR} más (sube el umbral con --umbral para ver solo las peores).")

    print(f"\n2. FRASES CASI IDÉNTICAS DENTRO DE UN MISMO PROCEDIMIENTO (>= {UMBRAL_DUPLICADA})")
    if not duplicadas:
        print("   Ninguna.")
    for s, i, j in sorted(duplicadas, reverse=True)[:MOSTRAR]:
        print(f"   {s:.3f}  [{ids[i]}] {frases[i]!r} ~ {frases[j]!r}")

    print("\n3. QUÉ TAN CERCA ESTÁN LOS PROCEDIMIENTOS ENTRE SÍ (frase más parecida de cada par)")
    for (a, b), (s, i, j) in sorted(mejor_entre_procedimientos.items(), key=lambda kv: kv[1][0], reverse=True):
        print(f"   {s:.3f}  {a} <-> {b}")


if __name__ == "__main__":
    main()
