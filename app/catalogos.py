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
# 'No verificado': aún no subió su certificado. 'En Verificación': lo subió y se está revisando.
ESTADOS_VERIFICACION = ("No verificado", "En Verificación", "Activo", "Rechazado")
ESTADOS_CERTIFICADO = ("Pendiente", "Aprobada", "Rechazada")


def sql_in(valores) -> str:
    """('a','b') -> "'a', 'b'" para usar dentro de un CheckConstraint."""
    return ", ".join(f"'{v}'" for v in valores)
