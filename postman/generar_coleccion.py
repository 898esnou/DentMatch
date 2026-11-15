"""
Genera la colección de Postman de DentMatch y, opcionalmente, la comprueba.

La colección se define UNA sola vez, en la lista PASOS de este archivo. De ahí salen:
  - postman/DentMatch.postman_collection.json   (se importa en Postman)
  - postman/DentMatch.local.postman_environment.json
  - la comprobación en Python (--probar), que repite los mismos pasos contra un servidor y
    verifica los mismos resultados esperados. Sirve para asegurar que la colección es correcta
    sin abrir Postman.

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python -m postman.generar_coleccion                      # solo genera los .json
    python -m postman.generar_coleccion --probar http://127.0.0.1:8011 admin@prueba.cl prueba123
"""
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
INTERNO = "Authorization"

# --------------------------------------------------------------------------- datos de apoyo
FUTURO = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%dT10:00:00")
PASADO = "2020-01-01T10:00:00"
SOLICITUD = {
    "titulo": "Dolor en molar inferior",
    "descripcion": "Me duele al masticar en una muela de abajo desde hace una semana",
    "area": "endodoncia", "urgente": True, "comuna": "Providencia", "disponibilidad": "Martes por la tarde",
}

# Código que Postman ejecuta antes de "Registrar paciente": inventa RUT válidos y correos únicos
# para que la colección se pueda correr muchas veces sin chocar con datos anteriores.
PRE_DATOS_UNICOS = """
const dv = (cuerpo) => { let s = 0, m = 2; const t = String(cuerpo);
  for (let i = t.length - 1; i >= 0; i--) { s += Number(t[i]) * m; m = (m === 7) ? 2 : m + 1; }
  const r = 11 - (s % 11); return r === 11 ? '0' : (r === 10 ? 'K' : String(r)); };
const rutNuevo = () => { const c = Math.floor(10000000 + Math.random() * 39000000);
  return String(c).replace(/\\B(?=(\\d{3})+(?!\\d))/g, '.') + '-' + dv(c); };
const s = Date.now();
pm.collectionVariables.set('sufijo', String(s));
pm.collectionVariables.set('rutPaciente', rutNuevo());
pm.collectionVariables.set('rutEstudiante', rutNuevo());
pm.collectionVariables.set('rutPaciente2', rutNuevo());
pm.collectionVariables.set('fechaFutura', new Date(s + 10 * 86400000).toISOString().slice(0, 19));
""".strip()


def p(carpeta, nombre, metodo, ruta, quien=None, ok=200, json_=None, form=None, guarda=None, campos=None,
      sin=None, lista=False, pre=None, descripcion=""):
    """Un paso de la colección.
    quien: rol que envía el token (None = sin sesión). ok: código HTTP esperado.
    guarda: {variable: campo de la respuesta}. campos: {campo: valor esperado | None si solo debe existir}.
    sin: textos que NO deben aparecer en la respuesta (datos privados). lista: la respuesta debe ser una lista."""
    return dict(carpeta=carpeta, nombre=nombre, metodo=metodo, ruta=ruta, quien=quien, ok=ok, json=json_, form=form,
                guarda=guarda or {}, campos=campos or {}, sin=sin or [], lista=lista, pre=pre, descripcion=descripcion)


C0, C1, C2, C3, C4, C5, C6, C7, C8, C9 = (
    "0. Preparación", "1. Autenticación", "2. Seguridad y roles", "3. Solicitudes", "4. Requerimientos",
    "5. Postulaciones y citas", "6. Chat y moderación", "7. Panel de administración",
    "8. Baneo por advertencias", "9. Búsqueda y cierre")


def reg(rol, quien_var, extra=None):
    d = {"nombre_completo": "{{nombre}}", "rut": "{{rut}}", "correo": "{{correo}}", "contrasena": "123456", "rol": rol}
    d.update(extra or {})
    return d


PASOS = [
    # ------------------------------------------------------------------ 0. Preparación
    p(C0, "Registrar paciente", "POST", "/api/registro", ok=201, pre=PRE_DATOS_UNICOS,
      form={"nombre_completo": "Paciente Postman", "rut": "{{rutPaciente}}", "correo": "paciente.{{sufijo}}@postman.cl",
            "contrasena": "123456", "rol": "paciente"},
      guarda={"pacienteId": "id"}, campos={"rol": "paciente"},
      descripcion="Crea un paciente con RUT válido y correo únicos (los inventa el script previo)."),
    p(C0, "Registrar estudiante", "POST", "/api/registro", ok=201,
      form={"nombre_completo": "Estudiante Postman", "rut": "{{rutEstudiante}}", "correo": "estudiante.{{sufijo}}@postman.cl",
            "contrasena": "123456", "rol": "estudiante", "universidad": "Universidad de Chile", "ano_carrera": "5"},
      guarda={"estudianteId": "id"}, campos={"rol": "estudiante"}),
    p(C0, "Registrar segundo paciente", "POST", "/api/registro", ok=201,
      form={"nombre_completo": "Paciente Dos Postman", "rut": "{{rutPaciente2}}", "correo": "paciente2.{{sufijo}}@postman.cl",
            "contrasena": "123456", "rol": "paciente"},
      guarda={"paciente2Id": "id"}),
    p(C0, "Iniciar sesión como paciente", "POST", "/api/login", json_={"correo": "paciente.{{sufijo}}@postman.cl", "contrasena": "123456"},
      guarda={"tokenPaciente": "access_token"}, campos={"access_token": None}),
    p(C0, "Iniciar sesión como estudiante", "POST", "/api/login", json_={"correo": "estudiante.{{sufijo}}@postman.cl", "contrasena": "123456"},
      guarda={"tokenEstudiante": "access_token"}),
    p(C0, "Iniciar sesión como segundo paciente", "POST", "/api/login", json_={"correo": "paciente2.{{sufijo}}@postman.cl", "contrasena": "123456"},
      guarda={"tokenPaciente2": "access_token"}),
    p(C0, "Iniciar sesión como administrador", "POST", "/api/login", json_={"correo": "{{adminCorreo}}", "contrasena": "{{adminContrasena}}"},
      guarda={"tokenAdmin": "access_token"},
      descripcion="Requiere un administrador ya creado (python -m scripts.crear_admin). Sus datos van en las variables adminCorreo y adminContrasena."),
    p(C0, "Admin verifica al estudiante", "PATCH", "/api/admin/estudiantes/{{estudianteId}}/verificacion", quien="admin",
      json_={"estado": "Activo"}, campos={"estado_verificacion": "Activo"},
      descripcion="Un estudiante nuevo no puede postular ni chatear hasta que el administrador lo verifique."),

    # ------------------------------------------------------------------ 1. Autenticación
    p(C1, "Registro con rol admin es rechazado", "POST", "/api/registro", ok=400,
      form={"nombre_completo": "Intruso", "rut": "{{rutPaciente}}", "correo": "intruso.{{sufijo}}@postman.cl", "contrasena": "123456", "rol": "admin"},
      descripcion="El registro público nunca crea administradores."),
    p(C1, "Registro con RUT inválido", "POST", "/api/registro", ok=400,
      form={"nombre_completo": "RUT Malo", "rut": "12.345.678-9", "correo": "rutmalo.{{sufijo}}@postman.cl", "contrasena": "123456", "rol": "paciente"}),
    p(C1, "Registro con RUT repetido", "POST", "/api/registro", ok=400,
      form={"nombre_completo": "Repetido", "rut": "{{rutPaciente}}", "correo": "repetido.{{sufijo}}@postman.cl", "contrasena": "123456", "rol": "paciente"}),
    p(C1, "Registro con correo repetido", "POST", "/api/registro", ok=400,
      form={"nombre_completo": "Repetido", "rut": "{{rutPaciente2}}", "correo": "paciente.{{sufijo}}@postman.cl", "contrasena": "123456", "rol": "paciente"}),
    p(C1, "Estudiante de 3er año es rechazado", "POST", "/api/registro", ok=400,
      form={"nombre_completo": "Muy Nuevo", "rut": "{{rutPaciente}}", "correo": "tercero.{{sufijo}}@postman.cl", "contrasena": "123456",
            "rol": "estudiante", "universidad": "Universidad de Chile", "ano_carrera": "3"}),
    p(C1, "Contraseña incorrecta", "POST", "/api/login", ok=401,
      json_={"correo": "paciente.{{sufijo}}@postman.cl", "contrasena": "equivocada"}),
    p(C1, "Consultar /me sin sesión", "GET", "/api/me", ok=401),
    p(C1, "Consultar /me como paciente", "GET", "/api/me", quien="paciente", campos={"rol": "paciente"}),

    # ------------------------------------------------------------------ 2. Seguridad y roles
    p(C2, "Paciente no accede a requerimientos", "GET", "/api/requerimientos", quien="paciente", ok=403),
    p(C2, "Estudiante no publica solicitudes", "POST", "/api/solicitudes", quien="estudiante", ok=403, json_=SOLICITUD),
    p(C2, "Paciente no entra al panel admin", "GET", "/api/admin/estudiantes", quien="paciente", ok=403),
    p(C2, "Estudiante no entra a los reportes", "GET", "/api/admin/reportes", quien="estudiante", ok=403),
    p(C2, "Sin sesión no hay solicitudes", "GET", "/api/solicitudes", ok=401),

    # ------------------------------------------------------------------ 3. Solicitudes
    p(C3, "Paciente publica una solicitud", "POST", "/api/solicitudes", quien="paciente", ok=201, json_=SOLICITUD,
      guarda={"solicitudId": "id"}, campos={"estado": None, "titulo": "Dolor en molar inferior"}),
    p(C3, "Descripción demasiado corta", "POST", "/api/solicitudes", quien="paciente", ok=422,
      json_={"titulo": "Algo", "descripcion": "corta", "area": "endodoncia"}),
    p(C3, "Descripción de más de 500 caracteres", "POST", "/api/solicitudes", quien="paciente", ok=422,
      json_={"titulo": "Texto largo", "descripcion": "x" * 501, "area": "endodoncia"}),
    p(C3, "Área inexistente", "POST", "/api/solicitudes", quien="paciente", ok=422,
      json_={"titulo": "Área mala", "descripcion": "Descripción suficientemente larga", "area": "magia"}),
    p(C3, "Paciente lista sus solicitudes", "GET", "/api/solicitudes", quien="paciente", lista=True),
    p(C3, "Paciente edita su solicitud", "PATCH", "/api/solicitudes/{{solicitudId}}", quien="paciente",
      json_={"titulo": "Dolor en molar (editado)"}, campos={"titulo": "Dolor en molar (editado)"}),
    p(C3, "Otro paciente no ve la solicitud ajena", "GET", "/api/solicitudes/{{solicitudId}}", quien="paciente2", ok=404),
    p(C3, "Estudiante ve los casos sin datos privados", "GET", "/api/casos", quien="estudiante", lista=True,
      sin=["rut", "correo", "paciente.{{sufijo}}@postman.cl"],
      descripcion="Comprueba que la respuesta no contiene RUT ni correo de nadie."),

    # ------------------------------------------------------------------ 4. Requerimientos
    p(C4, "Estudiante declara un requerimiento", "POST", "/api/requerimientos", quien="estudiante", ok=201,
      json_={"tratamiento": "Endodoncia unirradicular", "area": "endodoncia", "tutor": "Prof. Ricardo", "cantidad_requerida": 2},
      guarda={"requerimientoId": "id"}, campos={"estado": None}),
    p(C4, "Requerimiento sin tutor", "POST", "/api/requerimientos", quien="estudiante", ok=422,
      json_={"tratamiento": "Endodoncia", "area": "endodoncia", "cantidad_requerida": 2}),
    p(C4, "Cantidad menor a 1", "POST", "/api/requerimientos", quien="estudiante", ok=422,
      json_={"tratamiento": "Endodoncia", "area": "endodoncia", "tutor": "Prof. Ricardo", "cantidad_requerida": 0}),
    p(C4, "Estudiante lista sus requerimientos", "GET", "/api/requerimientos", quien="estudiante", lista=True),
    p(C4, "Paciente2 no puede registrar avance ajeno", "POST", "/api/requerimientos/{{requerimientoId}}/avance", quien="paciente2", ok=403, json_={"cantidad": 1}),

    # ------------------------------------------------------------------ 5. Postulaciones y citas
    p(C5, "Estudiante postula al caso", "POST", "/api/postulaciones", quien="estudiante", ok=201,
      json_={"solicitud_id": "{{solicitudId}}", "requerimiento_id": "{{requerimientoId}}", "mensaje": "Puedo atenderte."},
      guarda={"postulacionId": "id"}, campos={"estado": "Pendiente"}),
    p(C5, "No se puede postular dos veces", "POST", "/api/postulaciones", quien="estudiante", ok=409,
      json_={"solicitud_id": "{{solicitudId}}", "requerimiento_id": "{{requerimientoId}}"}),
    p(C5, "No se puede escribir hasta que se acepta", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="estudiante", ok=409,
      json_={"contenido": "Hola, ¿cómo estás?"}),
    p(C5, "El estudiante no responde su propia postulación", "POST", "/api/postulaciones/{{postulacionId}}/responder", quien="estudiante", ok=403,
      json_={"accion": "aceptar"}),
    p(C5, "Paciente acepta la postulación", "POST", "/api/postulaciones/{{postulacionId}}/responder", quien="paciente",
      json_={"accion": "aceptar"}, campos={"estado": "Aceptada"}),
    p(C5, "Cita con fecha pasada es rechazada", "POST", "/api/citas", quien="estudiante", ok=422,
      json_={"postulacion_id": "{{postulacionId}}", "fecha_hora": PASADO, "lugar": "Clínica"}),
    p(C5, "Estudiante agenda una cita", "POST", "/api/citas", quien="estudiante", ok=201,
      json_={"postulacion_id": "{{postulacionId}}", "fecha_hora": "{{fechaFutura}}", "lugar": "Clínica odontológica"},
      guarda={"citaId": "id"}, campos={"estado": "Agendada"}),
    p(C5, "Paciente lista sus citas", "GET", "/api/citas", quien="paciente", lista=True),
    p(C5, "Paciente no puede marcar la cita como realizada", "PATCH", "/api/citas/{{citaId}}", quien="paciente", ok=403,
      json_={"estado": "Realizada"}),

    # ------------------------------------------------------------------ 6. Chat y moderación
    p(C6, "Paciente envía un mensaje", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="paciente", ok=201,
      json_={"contenido": "Hola, ¿te sirve el martes a las 15:30?"}, campos={"contenido": None}),
    p(C6, "Estudiante responde", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="estudiante", ok=201,
      json_={"contenido": "Hola, sí, nos vemos el martes en la clínica."}),
    p(C6, "Mensaje vacío es rechazado", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="paciente", ok=422,
      json_={"contenido": "   "}),
    p(C6, "Un mensaje clínico normal pasa la moderación", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="paciente", ok=201,
      json_={"contenido": "Me duele mucho la muela y tengo sangrado de la encía"},
      descripcion="Los términos clínicos no se confunden con ofensas."),
    p(C6, "Mensaje ofensivo se bloquea (advertencia 1)", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="estudiante", ok=422,
      json_={"contenido": "eres un idiota"},
      descripcion="No le llega a la otra persona y queda como advertencia."),
    p(C6, "La otra persona no recibe el mensaje bloqueado", "GET", "/api/chat/{{postulacionId}}/mensajes", quien="paciente",
      sin=["eres un idiota"]),
    p(C6, "Paciente reporta la conversación", "POST", "/api/chat/{{postulacionId}}/reportar", quien="paciente", ok=201,
      json_={"motivo": "El estudiante me insultó en el chat"}, guarda={"reporteId": "id"}),
    p(C6, "No se puede reportar dos veces", "POST", "/api/chat/{{postulacionId}}/reportar", quien="paciente", ok=409,
      json_={"motivo": "El estudiante me insultó en el chat"}),
    p(C6, "Motivo del reporte demasiado corto", "POST", "/api/chat/{{postulacionId}}/reportar", quien="estudiante", ok=422,
      json_={"motivo": "mal"}),
    p(C6, "Paciente archiva la conversación", "POST", "/api/chat/{{postulacionId}}/archivar", quien="paciente"),
    p(C6, "No se escribe en un chat archivado", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="estudiante", ok=409,
      json_={"contenido": "¿Seguimos?"}),
    p(C6, "El estudiante no puede reabrir lo que archivó el paciente", "POST", "/api/chat/{{postulacionId}}/reabrir", quien="estudiante", ok=403),
    p(C6, "Paciente reabre la conversación", "POST", "/api/chat/{{postulacionId}}/reabrir", quien="paciente"),
    p(C6, "Se puede volver a escribir", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="estudiante", ok=201,
      json_={"contenido": "Listo, te espero el martes."}),
    p(C6, "Avisos del paciente", "GET", "/api/avisos", quien="paciente", lista=True),

    # ------------------------------------------------------------------ 7. Panel de administración
    p(C7, "Admin ve el resumen", "GET", "/api/admin/resumen", quien="admin"),
    p(C7, "Admin lista los reportes", "GET", "/api/admin/reportes", quien="admin", lista=True),
    p(C7, "Admin ve el detalle con la evidencia", "GET", "/api/admin/reportes/{{reporteId}}", quien="admin", campos={"id": None}),
    p(C7, "Suspensión sin días es rechazada", "POST", "/api/admin/reportes/{{reporteId}}/resolver", quien="admin", ok=422,
      json_={"decision": "suspension"}),
    p(C7, "Admin descarta el reporte", "POST", "/api/admin/reportes/{{reporteId}}/resolver", quien="admin",
      json_={"decision": "descartar", "nota": "Prueba con Postman"}),
    p(C7, "Un reporte resuelto no se resuelve dos veces", "POST", "/api/admin/reportes/{{reporteId}}/resolver", quien="admin", ok=409,
      json_={"decision": "descartar"}),
    p(C7, "Admin lista las cuentas", "GET", "/api/admin/cuentas", quien="admin", lista=True),
    p(C7, "Admin lista los estudiantes en verificación", "GET", "/api/admin/estudiantes", quien="admin", lista=True),
    p(C7, "Rechazo de estudiante sin motivo", "PATCH", "/api/admin/estudiantes/{{estudianteId}}/verificacion", quien="admin", ok=422,
      json_={"estado": "Rechazado"}),

    # ------------------------------------------------------------------ 8. Baneo por 3 advertencias
    p(C8, "Paciente2 publica una solicitud", "POST", "/api/solicitudes", quien="paciente2", ok=201, json_=SOLICITUD,
      guarda={"solicitud2Id": "id"}),
    p(C8, "Estudiante postula a la solicitud 2", "POST", "/api/postulaciones", quien="estudiante", ok=201,
      json_={"solicitud_id": "{{solicitud2Id}}"}, guarda={"postulacion2Id": "id"}),
    p(C8, "Paciente2 acepta", "POST", "/api/postulaciones/{{postulacion2Id}}/responder", quien="paciente2", json_={"accion": "aceptar"}),
    p(C8, "Primer insulto: advertencia 1 de 3", "POST", "/api/chat/{{postulacion2Id}}/mensajes", quien="paciente2", ok=422,
      json_={"contenido": "eres un idiota"}),
    p(C8, "Segundo insulto: advertencia 2 de 3", "POST", "/api/chat/{{postulacion2Id}}/mensajes", quien="paciente2", ok=422,
      json_={"contenido": "qué imbécil eres"}),
    p(C8, "Tercer insulto: la cuenta se banea", "POST", "/api/chat/{{postulacion2Id}}/mensajes", quien="paciente2", ok=403,
      json_={"contenido": "hijo de puta"},
      descripcion="3 advertencias en 30 días suspenden la cuenta, cancelan sus vínculos y crean un reporte automático."),
    p(C8, "El baneo genera un reporte automático", "GET", "/api/admin/reportes", quien="admin", lista=True),
    p(C8, "Admin levanta la sanción", "POST", "/api/admin/cuentas/{{paciente2Id}}/levantar-sancion", quien="admin"),

    # ------------------------------------------------------------------ 9. Cierre del flujo
    p(C9, "Búsqueda con texto demasiado corto", "POST", "/api/busqueda", quien="paciente", ok=422, json_={"texto": "a"}),
    p(C9, "El estudiante no puede usar la búsqueda", "POST", "/api/busqueda", quien="estudiante", ok=403,
      json_={"texto": "necesito una limpieza dental"}),
    p(C9, "Estudiante completa el tratamiento", "POST", "/api/postulaciones/{{postulacionId}}/completar", quien="estudiante"),
    p(C9, "El requerimiento sumó avance", "GET", "/api/requerimientos/{{requerimientoId}}", quien="estudiante", campos={"cantidad_completada": 1}),
    p(C9, "El chat queda en solo lectura", "POST", "/api/chat/{{postulacionId}}/mensajes", quien="paciente", ok=409,
      json_={"contenido": "Gracias por todo"}),
]

TOKEN = {"admin": "tokenAdmin", "paciente": "tokenPaciente", "estudiante": "tokenEstudiante", "paciente2": "tokenPaciente2"}


# --------------------------------------------------------------------------- salida para Postman
def _js(paso):
    lineas = [f"pm.test('Responde {paso['ok']}', () => pm.response.to.have.status({paso['ok']}));"]
    if paso["lista"]:
        lineas.append("pm.test('La respuesta es una lista', () => pm.expect(pm.response.json()).to.be.an('array'));")
    for campo, valor in paso["campos"].items():
        if valor is None:
            lineas.append(f"pm.test('La respuesta trae {campo}', () => pm.expect(pm.response.json()).to.have.property('{campo}'));")
        else:
            lineas.append(f"pm.test('{campo} = {valor}', () => pm.expect(pm.response.json().{campo}).to.eql({json.dumps(valor)}));")
    for texto in paso["sin"]:
        lineas.append(
            f"pm.test('No expone \"{texto}\"', () => pm.expect(pm.response.text().toLowerCase()).to.not.include(pm.variables.replaceIn({json.dumps(texto.lower())})));")
    if paso["guarda"]:
        lineas.append("if (pm.response.code < 300) { const d = pm.response.json();")
        for var, campo in paso["guarda"].items():
            lineas.append(f"  pm.collectionVariables.set('{var}', d.{campo});")
        lineas.append("}")
    return lineas


def _item(paso):
    req = {"method": paso["metodo"], "header": [], "url": {"raw": "{{base_url}}" + paso["ruta"], "host": ["{{base_url}}"],
           "path": paso["ruta"].strip("/").split("/")}}
    if paso["quien"]:
        req["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{" + TOKEN[paso["quien"]] + "}}", "type": "string"}]}
    else:
        req["auth"] = {"type": "noauth"}
    if paso["json"] is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        crudo = json.dumps(paso["json"], ensure_ascii=False, indent=2)
        crudo = re.sub(r'"\{\{(\w+Id)\}\}"', r"{{\1}}", crudo)  # los ids van como número, sin comillas
        req["body"] = {"mode": "raw", "raw": crudo, "options": {"raw": {"language": "json"}}}
    elif paso["form"] is not None:
        req["body"] = {"mode": "urlencoded", "urlencoded": [{"key": k, "value": v, "type": "text"} for k, v in paso["form"].items()]}
    if paso["descripcion"]:
        req["description"] = paso["descripcion"]
    eventos = [{"listen": "test", "script": {"type": "text/javascript", "exec": _js(paso)}}]
    if paso["pre"]:
        eventos.insert(0, {"listen": "prerequest", "script": {"type": "text/javascript", "exec": paso["pre"].splitlines()}})
    return {"name": paso["nombre"], "event": eventos, "request": req}


def _numeros_sin_comillas(raw):
    # En Postman los ids van como número: "{{solicitudId}}" se reemplaza por el valor tal cual.
    return raw


def generar():
    carpetas = {}
    for paso in PASOS:
        carpetas.setdefault(paso["carpeta"], []).append(_item(paso))
    coleccion = {
        "info": {
            "name": "DentMatch API",
            "description": "Pruebas de la API de DentMatch. Ejecutar la colección completa, en orden, con Collection Runner. "
                           "Ver pruebas/Pruebas_postman.md.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [{"name": nombre, "item": items} for nombre, items in carpetas.items()],
        "variable": [
            {"key": "base_url", "value": "http://127.0.0.1:8011"},
            {"key": "adminCorreo", "value": "admin@prueba.cl"},
            {"key": "adminContrasena", "value": "prueba123"},
        ],
    }
    entorno = {
        "name": "DentMatch local",
        "values": [
            {"key": "base_url", "value": "http://127.0.0.1:8011", "type": "default", "enabled": True},
            {"key": "adminCorreo", "value": "admin@prueba.cl", "type": "default", "enabled": True},
            {"key": "adminContrasena", "value": "prueba123", "type": "secret", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
    }
    with open(os.path.join(AQUI, "DentMatch.postman_collection.json"), "w", encoding="utf-8") as f:
        json.dump(coleccion, f, ensure_ascii=False, indent=2)
    with open(os.path.join(AQUI, "DentMatch.local.postman_environment.json"), "w", encoding="utf-8") as f:
        json.dump(entorno, f, ensure_ascii=False, indent=2)
    print(f"Colección generada: {len(PASOS)} peticiones en {len(carpetas)} carpetas.")


# --------------------------------------------------------------------------- comprobación en Python
def _dv(c):
    s, m = 0, 2
    for d in reversed(str(c)):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    r = 11 - s % 11
    return "0" if r == 11 else "K" if r == 10 else str(r)


def _rut():
    c = random.randint(10_000_000, 49_999_999)
    return f"{c:,}".replace(",", ".") + "-" + _dv(c)


def probar(base, admin_correo, admin_pass):
    import httpx

    v = {"adminCorreo": admin_correo, "adminContrasena": admin_pass, "fechaFutura": FUTURO,
         "sufijo": str(random.randint(10**9, 10**10))}
    for k in ("rutPaciente", "rutEstudiante", "rutPaciente2"):
        v[k] = _rut()

    def sub(x):
        if isinstance(x, str):
            for k, val in v.items():
                x = x.replace("{{" + k + "}}", str(val))
            return x
        if isinstance(x, dict):
            return {k: sub(val) for k, val in x.items()}
        return x

    fallos, total = [], 0
    with httpx.Client(base_url=base, timeout=30) as c:
        for paso in PASOS:
            if paso["pre"]:
                pass  # el script de Postman equivale a los datos que ya generó este bloque
            # ids numéricos: se envían como número en JSON, igual que hace Postman al reemplazar la variable
            cuerpo = json.dumps(paso["json"]) if paso["json"] is not None else None
            if cuerpo:
                for k, val in v.items():
                    cuerpo = cuerpo.replace('"{{' + k + '}}"', str(val) if str(val).isdigit() else json.dumps(val))
                    cuerpo = cuerpo.replace("{{" + k + "}}", str(val))
            ruta = sub(paso["ruta"])
            hdr = {}
            if paso["quien"]:
                hdr["Authorization"] = "Bearer " + v[TOKEN[paso["quien"]]]
            if cuerpo:
                hdr["Content-Type"] = "application/json"
            data = {k: sub(x) for k, x in paso["form"].items()} if paso["form"] else None
            r = c.request(paso["metodo"], ruta, headers=hdr, content=cuerpo, data=data)
            total += 1
            problemas = []
            if r.status_code != paso["ok"]:
                problemas.append(f"esperaba {paso['ok']} y respondió {r.status_code}: {r.text[:200]}")
            else:
                try:
                    d = r.json()
                except Exception:
                    d = None
                if paso["lista"] and not isinstance(d, list):
                    problemas.append("no es una lista")
                for campo, valor in paso["campos"].items():
                    if not isinstance(d, dict) or campo not in d:
                        problemas.append(f"falta {campo}")
                    elif valor is not None and d[campo] != valor:
                        problemas.append(f"{campo}={d[campo]!r}, esperaba {valor!r}")
                for texto in paso["sin"]:
                    if sub(texto).lower() in r.text.lower():
                        problemas.append(f"expone «{texto}»")
                if r.status_code < 300 and isinstance(d, dict):
                    for var, campo in paso["guarda"].items():
                        v[var] = d.get(campo)
            marca = "OK " if not problemas else "FALLA"
            print(f"{marca} {paso['carpeta'][:2]} {paso['metodo']:6} {paso['nombre']}" + ("" if not problemas else "  -> " + "; ".join(problemas)))
            if problemas:
                fallos.append(paso["nombre"])
    print(f"\n{total - len(fallos)} de {total} peticiones correctas.")
    return 1 if fallos else 0


if __name__ == "__main__":
    generar()
    if len(sys.argv) >= 5 and sys.argv[1] == "--probar":
        sys.exit(probar(sys.argv[2], sys.argv[3], sys.argv[4]))
