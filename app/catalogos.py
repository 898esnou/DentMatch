"""
Valores fijos que comparten backend y frontend (áreas clínicas, estados, días).
Si agregas un valor aquí, se acepta automáticamente en toda la API.
"""

# clave interna -> nombre para mostrar
AREAS = {
    "prevencion": "Limpieza y Prevención",
    "operatoria": "Operatoria Dental",
    "endodoncia": "Endodoncia",
    "periodoncia": "Periodoncia",
    "rehabilitacion": "Rehabilitación Oral",
    "cirugia": "Cirugía y Extracciones",
    "diagnostico": "Diagnóstico General",
    "otra": "Otra",
}

DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")

ESTADOS_REQUERIMIENTO = ("Abierto", "Completado", "Cancelado")
ESTADOS_SOLICITUD = ("Abierta", "En Revisión", "Asignada", "Completada", "Cancelada")
ESTADOS_POSTULACION = ("Pendiente", "Aceptada", "Rechazada", "Cancelada")
ESTADOS_CITA = ("Agendada", "Realizada", "Cancelada")
ESTADOS_VERIFICACION = ("En Verificación", "Activo", "Rechazado")


def sql_in(valores) -> str:
    """('a','b') -> "'a', 'b'" para usar dentro de un CheckConstraint."""
    return ", ".join(f"'{v}'" for v in valores)
