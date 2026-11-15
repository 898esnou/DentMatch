# Pruebas de la API con Postman

> Documento hermano: [Pruebas_codigo.md](Pruebas_codigo.md) (pruebas automáticas del código).

Colección de Postman que recorre la API de DentMatch como lo haría cada rol (paciente, estudiante y administrador) y comprueba las respuestas. Complementa a las pruebas automáticas de `tests/` (ver `Pruebas_codigo.md`, en esta misma carpeta): esas se ejecutan por código; esta se ve y se ejecuta con una herramienta visual, útil para demostrar el sistema y para evidencia.

**80 peticiones en 10 carpetas. Cada una incluye sus pruebas (`pm.test`) y las variables se encadenan solas** (el token y los ids que devuelve una petición los usa la siguiente).

## Archivos
Este documento está en `pruebas/`; los archivos de la colección están en `postman/`.

| Archivo | Para qué sirve |
|---|---|
| `postman/DentMatch.postman_collection.json` | La colección, para importar en Postman |
| `postman/DentMatch.local.postman_environment.json` | Entorno con la dirección del servidor y el administrador de prueba |
| `postman/servidor_prueba.py` | Servidor local con base temporal y un administrador de prueba, para ejecutar la colección sin riesgo |
| `postman/reporte_newman.html` | Reporte de la última ejecución con Newman (evidencia) |
| `postman/generar_coleccion.py` | Define los pasos una sola vez y genera los dos archivos anteriores. También puede comprobar la colección sin Postman (ver más abajo) |

## Cómo usarla

### 1. Levantar el servidor de prueba
**No ejecutar contra la base real de Supabase:** la colección crea usuarios, solicitudes y reportes. Para eso existe `servidor_prueba.py`, que usa una base SQLite temporal, ignora el `.env` y crea un administrador de prueba (`admin@prueba.cl` / `prueba123`). El administrador es necesario porque el registro público no lo permite, y la colección lo usa para verificar al estudiante y revisar reportes.

```bash
python -m postman.servidor_prueba
```

Queda escuchando en `http://127.0.0.1:8011` (otro puerto: `python -m postman.servidor_prueba 8020`). La base es nueva cada vez que se inicia.

### 2. Importar en Postman
1. **Import** → seleccionar `DentMatch.postman_collection.json` y `DentMatch.local.postman_environment.json`.
2. Elegir el entorno **DentMatch local** (arriba a la derecha).
3. Los valores por defecto del entorno ya coinciden con el servidor de prueba (`base_url`, `adminCorreo`, `adminContrasena`). Solo hay que cambiarlos si se usa otro puerto o administrador.

### 3. Ejecutar
Clic derecho en la colección → **Run collection** → **Run**. Las peticiones deben ejecutarse **en orden** (es el orden por defecto), porque cada carpeta usa datos creados antes. Se puede repetir las veces que se quiera: los RUT y correos se inventan nuevos en cada corrida.

Resultado esperado: **las 80 peticiones con todas sus pruebas en verde.**

## Qué hace la colección

| Carpeta | Peticiones | Qué comprueba |
|---|---|---|
| 0. Preparación | 8 | Registra un paciente, un estudiante y un segundo paciente (con RUT válido y correo únicos); inicia sesión con los tres y con el administrador; el administrador verifica al estudiante |
| 1. Autenticación | 8 | Rechaza el registro con rol admin, RUT inválido, RUT o correo repetido y estudiante de 3er año; contraseña incorrecta (401); `/api/me` sin sesión (401) y con sesión |
| 2. Seguridad y roles | 5 | Cada rol solo accede a lo suyo (403) y sin sesión se rechaza (401) |
| 3. Solicitudes | 8 | Publicar (201), validar descripción corta, de más de 500 caracteres y área inexistente (422), listar, editar, que otro paciente no vea la solicitud ajena (404) y que el estudiante vea los casos **sin RUT ni correo** |
| 4. Requerimientos | 5 | Declarar un requerimiento, rechazar sin tutor o con cantidad 0 (422), listar y bloquear a quien no es el estudiante dueño (403) |
| 5. Postulaciones y citas | 9 | Postular, no postular dos veces (409), no escribir antes de aceptar (409), que el estudiante no responda su propia postulación, aceptar, rechazar cita con fecha pasada, agendar, listar y que el paciente no pueda marcar la cita como realizada |
| 6. Chat y moderación | 15 | Enviar y responder mensajes; rechazar vacíos; dejar pasar un mensaje clínico normal; bloquear un insulto (advertencia) sin que llegue a la otra persona; reportar (y no dos veces); archivar, bloquear escritura en chat archivado, reabrir solo quien archivó; avisos |
| 7. Panel de administración | 9 | Resumen, listar reportes, ver el detalle con evidencia, exigir días en una suspensión, descartar un reporte (y no resolverlo dos veces), listar cuentas y estudiantes, exigir motivo al rechazar a un estudiante |
| 8. Baneo por advertencias | 8 | Con otra pareja paciente–estudiante: tres insultos seguidos dan advertencia 1, advertencia 2 y baneo (403); el baneo genera un reporte automático y el administrador levanta la sanción |
| 9. Búsqueda y cierre | 5 | Búsqueda con texto corto (422) y bloqueada para estudiantes (403); el estudiante completa el tratamiento, el requerimiento suma avance y el chat queda en solo lectura |

Cada petición tiene su código HTTP esperado (201, 400, 401, 403, 404, 409, 422 o 200) y, según el caso, comprueba campos de la respuesta, que sea una lista o que no aparezcan datos privados.

## Lo que no cubre la colección
- **Subir el certificado** (`POST /api/verificacion/certificado`) y la **búsqueda con IA** completa: dependen de un archivo real y de la API de Gemini. Quedan cubiertas por las pruebas automáticas, que simulan esos servicios.
- **Las pantallas** (HTML y JavaScript): son un recorrido manual (ver sección 3 de `Pruebas_codigo.md`).

## Ejecutar desde la consola con Newman
Newman es el ejecutor oficial de Postman por línea de comandos: corre la misma colección, con sus scripts, y no necesita abrir la aplicación. Requiere Node.js.

```bash
npm install -g newman newman-reporter-htmlextra
newman run postman/DentMatch.postman_collection.json -e postman/DentMatch.local.postman_environment.json -r htmlextra --reporter-htmlextra-export postman/reporte_newman.html
```

El servidor de prueba debe estar encendido (paso 1). `reporte_newman.html` es el reporte visual de la última corrida, útil como evidencia; se abre con cualquier navegador.

**Última ejecución con Newman (14-11-2026):** 80 peticiones, 80 scripts de prueba y 108 verificaciones; **0 fallidas**. Duración total: 13 s.

## Comprobar la colección sin Postman ni Node
`generar_coleccion.py` repite los mismos 80 pasos con Python y verifica los mismos resultados. Sirve para confirmar, por ejemplo en una revisión, que la colección sigue correcta aunque cambie el código:

```bash
python -m postman.generar_coleccion --probar http://127.0.0.1:8011 admin@prueba.cl prueba123
```

Además regenera los archivos `.json`. Si se agrega o cambia un paso, se edita la lista `PASOS` de ese archivo y se vuelve a ejecutar; no se editan los `.json` a mano.

**Última comprobación:** 80 de 80 peticiones correctas (14-11-2026), contra un servidor local con base temporal.

## Notas
- El administrador del entorno es solo de prueba; no poner credenciales reales en un archivo que se suba a Git.
- El orden importa: la carpeta 8 y la 9 usan ids guardados por carpetas anteriores.
- Si una carpeta se ejecuta sola (por ejemplo, solo "6. Chat y moderación"), fallará porque le faltan los datos de la preparación. Ejecutar siempre la colección completa o, al menos, desde la carpeta 0.
