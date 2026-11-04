"""
Aviso de posible urgencia en la consulta del paciente.

NO es un diagnóstico: solo detecta palabras que suelen acompañar a una urgencia dental
(hinchazón en la cara, fiebre, pus, dificultad para tragar o respirar, golpes, dolor
insoportable) para sugerir que busque atención de inmediato, sin esperar a un estudiante.

Funciona con reglas simples y no usa IA ni sale del servidor: el texto del paciente no se
envía a ningún servicio externo por este motivo, no se guarda y no se escribe en los logs.
"""
import re
import unicodedata

MENSAJE_URGENCIA = (
    "Algunos de los síntomas que describes podrían necesitar atención rápida. Si tienes "
    "hinchazón en la cara o el cuello, fiebre, pus, dificultad para tragar o respirar, un golpe "
    "reciente en la boca o un dolor que no puedes soportar, acude hoy mismo a un servicio de "
    "urgencia dental o a un centro de salud. DentMatch no reemplaza una atención de urgencia."
)

_PARTES_DEL_ROSTRO = r"\b(?:cara|mejilla|cuello|ojo|garganta|lengua|labio|mandibula)\b"

# Cada patrón trabaja sobre el texto en minúsculas y sin tildes.
_SENALES = [
    # Hinchazón o inflamación en el rostro o el cuello (no en las encías: eso es otra cosa).
    re.compile(rf"(hinch\w*|inflam\w*).{{0,40}}{_PARTES_DEL_ROSTRO}|{_PARTES_DEL_ROSTRO}.{{0,40}}(hinch\w*|inflam\w*)"),
    re.compile(r"\bfiebre\b"),
    re.compile(r"\bpus\b|\babsceso\b|\bflemon\b"),
    re.compile(r"no (puedo|logro|alcanzo a) (tragar|respirar|abrir la boca)"),
    re.compile(r"(dificultad|problemas?) para (tragar|respirar|abrir la boca)"),
    re.compile(r"(no para de|no deja de|no se detiene el) sangrar|hemorragia"),
    re.compile(r"(golpe|golpee|golpeo|accidente|caida|me cai|choque).{0,50}(diente|muela|boca|mandibula)"),
    re.compile(r"(diente|muela|boca|mandibula).{0,50}(golpe|golpee|golpeo|accidente|caida|me cai|choque)"),
    re.compile(r"insoportable|no aguanto (el|mas)|no me deja dormir|dolor (muy )?(fuerte|intenso|terrible)"),
]


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def detectar_urgencia(texto: str) -> bool:
    """True si el texto menciona alguna señal de posible urgencia."""
    limpio = _normalizar(texto)
    return any(patron.search(limpio) for patron in _SENALES)
