"""
Evalúa la búsqueda semántica con casos de prueba (tests/casos_prueba.json).

Cada consulta se envía a la API UNA sola vez; los umbrales se prueban después,
sobre los mismos puntajes (así se gasta poca cuota).

Muestra, por caso, el puntaje del procedimiento esperado y del primero del ranking,
y al final el "margen" entre consultas correctas e irrelevantes: ese margen
decide qué umbral es seguro (ver README del proyecto / informe).

Uso (desde la raíz del proyecto):  python -m scripts.evaluar
"""
import json
from pathlib import Path

from dotenv import load_dotenv

# Este script corre aparte de la app, así que carga el .env él mismo.
load_dotenv(override=True)

from app.busqueda_semantica import (  # noqa: E402 (debe ir después de load_dotenv)
    construir_indice,
    embeber,
    nivel_coincidencia,
    ordenar_por_procedimiento,
)

RUTA_CASOS = Path(__file__).parent.parent / "tests" / "casos_prueba.json"
UMBRALES_A_PROBAR = [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]


def puntuar_casos(casos: list[dict]) -> list[dict]:
    """Calcula el ranking completo (sin umbral) de cada consulta, 1 llamada por consulta."""
    vectores, ids, _ = construir_indice()
    resultados = []
    for caso in casos:
        vector_consulta = embeber([caso["consulta"]], "RETRIEVAL_QUERY")[0]
        ranking = ordenar_por_procedimiento(vectores @ vector_consulta, ids, top_k=len(ids), umbral=0.0)
        resultados.append({**caso, "ranking": ranking})
    return resultados


def imprimir_detalle(resultados: list[dict]) -> None:
    """Una línea por caso: qué se esperaba, qué quedó primero y con qué puntaje."""
    print("DETALLE POR CONSULTA")
    for caso in resultados:
        primero_id, primero_puntaje = caso["ranking"][0]
        puntajes = dict(caso["ranking"])
        if caso["esperado"] is None:
            print(
                f"  [irrelevante] {primero_puntaje:.3f} {nivel_coincidencia(primero_puntaje)} "
                f"({primero_id})  {caso['consulta']!r}"
            )
        else:
            marca = "OK " if primero_id == caso["esperado"] else "MAL"
            print(
                f"  [{marca}] esperado={caso['esperado']} "
                f"({puntajes[caso['esperado']]:.3f} {nivel_coincidencia(puntajes[caso['esperado']])}) "
                f"primero={primero_id} ({primero_puntaje:.3f})  {caso['consulta']!r}"
            )
    print()


def imprimir_margen(resultados: list[dict]) -> None:
    """Compara el peor puntaje correcto contra el mejor puntaje irrelevante."""
    correctos = [
        dict(c["ranking"])[c["esperado"]] for c in resultados if c["esperado"] is not None
    ]
    irrelevantes = [c["ranking"][0][1] for c in resultados if c["esperado"] is None]
    peor_correcto = min(correctos)
    print(f"Peor puntaje de una consulta correcta:     {peor_correcto:.3f}")
    if irrelevantes:
        mejor_irrelevante = max(irrelevantes)
        print(f"Mejor puntaje de una consulta irrelevante: {mejor_irrelevante:.3f}")
        margen = peor_correcto - mejor_irrelevante
        print(f"Margen: {margen:.3f}  ->  un umbral seguro estaría entre ambos valores.")
        if margen <= 0:
            print("ATENCIÓN: no existe un umbral que separe bien estos casos.")
    print()


def imprimir_niveles(resultados: list[dict]) -> None:
    """Cuántas consultas correctas caen en cada nivel de coincidencia.

    Sirve para calibrar NIVEL_ALTO / NIVEL_MEDIO: si casi todas las correctas quedan
    en 'media', el umbral de 'alta' está demasiado exigente (y al revés).
    """
    conteo = {"alta": 0, "media": 0, "baja": 0}
    for caso in resultados:
        if caso["esperado"] is not None:
            conteo[nivel_coincidencia(dict(caso["ranking"])[caso["esperado"]])] += 1
    print(f"Consultas correctas por nivel de coincidencia: {conteo}\n")


def imprimir_tabla_umbrales(resultados: list[dict]) -> None:
    """Métricas por umbral, calculadas sin volver a llamar a la API."""
    con_esperado = [c for c in resultados if c["esperado"] is not None]
    sin_esperado = [c for c in resultados if c["esperado"] is None]
    for umbral in UMBRALES_A_PROBAR:
        top1 = sum(
            1 for c in con_esperado
            if c["ranking"][0][0] == c["esperado"] and c["ranking"][0][1] >= umbral
        )
        top3 = sum(
            1 for c in con_esperado
            if c["esperado"] in [i for i, p in c["ranking"][:3] if p >= umbral]
        )
        rechazos = sum(1 for c in sin_esperado if c["ranking"][0][1] < umbral)
        print(
            f"Umbral {umbral}: top-1 {top1}/{len(con_esperado)} | "
            f"top-3 {top3}/{len(con_esperado)} | "
            f"rechazos correctos {rechazos}/{len(sin_esperado)}"
        )


if __name__ == "__main__":
    casos_prueba = json.loads(RUTA_CASOS.read_text(encoding="utf-8"))
    resultados_puntuados = puntuar_casos(casos_prueba)
    imprimir_detalle(resultados_puntuados)
    imprimir_margen(resultados_puntuados)
    imprimir_niveles(resultados_puntuados)
    imprimir_tabla_umbrales(resultados_puntuados)
