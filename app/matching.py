"""
Puntaje de coincidencia entre un paciente y un estudiante (Historia 003 del backlog).

Combina tres variables, cada una entre 0 y 1:
  - procedimiento: qué tan parecida es la consulta al procedimiento que el estudiante
    necesita realizar (viene de la búsqueda semántica),
  - ubicación: si el estudiante atiende en la comuna del paciente,
  - disponibilidad: si coinciden los días y turnos que ambos declaran.

Cuando falta un dato (comuna "Por definir", disponibilidad vacía) no se premia ni se
castiga: esa variable cuenta como neutra (0.5), para no dejar al final de la lista a
quien simplemente no ha completado su perfil.

Todo son funciones puras (sin base de datos ni API) para poder probarlas fácilmente.
"""
import re
import unicodedata
from typing import List, Optional, Set, Tuple

PESO_PROCEDIMIENTO = 0.5
PESO_UBICACION = 0.3
PESO_DISPONIBILIDAD = 0.2
NEUTRO = 0.5
POR_PAGINA = 10

DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_TURNOS = {
    "manana": ("manana", "am", "a.m"),
    "tarde": ("tarde", "pm", "p.m"),
    "noche": ("noche",),
}
_COMUNA_SIN_DATO = {"", "por definir", "sin especificar", "sin definir"}
_CUALQUIERA = ("cualquier dia", "todos los dias", "cualquier horario", "flexible", "toda la semana", "siempre")


def normalizar(texto: Optional[str]) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


# ------------------------------------------------------------------ ubicación
def puntaje_ubicacion(comuna_paciente: Optional[str], comuna_estudiante: Optional[str]) -> Optional[float]:
    """1.0 si es la misma comuna, 0.0 si son distintas, None si falta alguno de los datos."""
    a, b = normalizar(comuna_paciente), normalizar(comuna_estudiante)
    if a in _COMUNA_SIN_DATO or b in _COMUNA_SIN_DATO:
        return None
    return 1.0 if a == b else 0.0


# ------------------------------------------------------------------ disponibilidad
def interpretar_disponibilidad(texto: Optional[str]) -> Tuple[Set[str], Set[str]]:
    """Extrae (días, turnos) de un texto libre como "lunes a viernes por la tarde".

    Entiende rangos ("lunes a miércoles"), "fines de semana" y frases como "cualquier día".
    """
    t = normalizar(texto)
    if not t:
        return set(), set()

    dias: Set[str] = set()
    turnos: Set[str] = set()

    if any(frase in t for frase in _CUALQUIERA):
        dias.update(DIAS)
        turnos.update(_TURNOS)

    for inicio, fin in re.findall(r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+(?:a|hasta|al)\s+(lunes|martes|miercoles|jueves|viernes|sabado|domingo)", t):
        i, f = DIAS.index(inicio), DIAS.index(fin)
        recorrido = range(i, f + 1) if i <= f else list(range(i, 7)) + list(range(0, f + 1))
        dias.update(DIAS[k] for k in recorrido)

    for dia in DIAS:
        if re.search(rf"\b{dia}s?\b", t):
            dias.add(dia)
    if "fin de semana" in t or "fines de semana" in t:
        dias.update(("sabado", "domingo"))

    for turno, palabras in _TURNOS.items():
        if any(re.search(rf"\b{re.escape(p)}\b", t) for p in palabras):
            turnos.add(turno)
    return dias, turnos


def puntaje_disponibilidad(texto_paciente: Optional[str], texto_estudiante: Optional[str]) -> Optional[float]:
    """Parte de los días y turnos del paciente que el estudiante también cubre (0 a 1).

    Devuelve None si no hay información comparable (alguno de los dos no dijo nada).
    """
    dias_p, turnos_p = interpretar_disponibilidad(texto_paciente)
    dias_e, turnos_e = interpretar_disponibilidad(texto_estudiante)

    componentes: List[float] = []
    if dias_p and dias_e:
        componentes.append(len(dias_p & dias_e) / len(dias_p))
    if turnos_p and turnos_e:
        componentes.append(len(turnos_p & turnos_e) / len(turnos_p))
    return sum(componentes) / len(componentes) if componentes else None


# ------------------------------------------------------------------ procedimiento
def puntaje_procedimiento(similitud: float, umbral: float) -> float:
    """Lleva la similitud de la búsqueda (de `umbral` a 1) a una escala de 0 a 1."""
    if similitud <= umbral:
        return 0.0
    return min((similitud - umbral) / (1.0 - umbral), 1.0)


# ------------------------------------------------------------------ puntaje final
def calcular_puntaje(
    procedimiento: float, ubicacion: Optional[float], disponibilidad: Optional[float]
) -> int:
    """Puntaje de coincidencia de 0 a 100 (los datos que faltan cuentan como neutros)."""
    u = NEUTRO if ubicacion is None else ubicacion
    d = NEUTRO if disponibilidad is None else disponibilidad
    total = PESO_PROCEDIMIENTO * procedimiento + PESO_UBICACION * u + PESO_DISPONIBILIDAD * d
    return round(100 * total)


def motivos_de_coincidencia(
    nombre_area: Optional[str], ubicacion: Optional[float], disponibilidad: Optional[float]
) -> List[str]:
    """Frases cortas que explican el puntaje (solo lo que suma a favor del estudiante)."""
    motivos: List[str] = []
    if nombre_area:
        motivos.append(f"Necesita pacientes de {nombre_area}")
    if ubicacion == 1.0:
        motivos.append("Atiende en tu comuna")
    if disponibilidad is not None and disponibilidad >= 0.5:
        motivos.append("Su disponibilidad coincide con la tuya")
    return motivos


# ------------------------------------------------------------------ paginación
def paginar(elementos: list, pagina: int, por_pagina: int = POR_PAGINA) -> Tuple[list, int]:
    """Devuelve (elementos de la página, total de páginas). Páginas desde 1."""
    total_paginas = max(1, -(-len(elementos) // por_pagina))  # división hacia arriba
    pagina = min(max(pagina, 1), total_paginas)
    inicio = (pagina - 1) * por_pagina
    return elementos[inicio : inicio + por_pagina], total_paginas
