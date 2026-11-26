# Pruebas de DentMatch: código y verificaciones

> Documento hermano: [Pruebas_postman.md](Pruebas_postman.md) (pruebas de la API con Postman).

Este documento describe todas las pruebas del proyecto: qué hace cada una, qué demuestra, quién la realizó y dónde está guardada. A medida que se agreguen funcionalidades al proyecto, se irán sumando nuevas pruebas y este documento se actualizará.

El proyecto tiene cuatro tipos de pruebas:

| Tipo | Qué es | Dónde está | Autor |
|---|---|---|---|
| Pruebas en video | Grabaciones del sistema funcionando | `Videos de Prueba/` y `Fase 1/Evidencias Grupales/` (en la raíz del repositorio) | Joaquín Rohland |
| Pruebas automáticas | Código que verifica solo que el backend se comporte bien | `tests/` | Benjamín Canales |
| Pruebas de API con Postman | Colección de 80 peticiones (108 verificaciones) que recorre la API como cada rol; ejecutada con Newman sin fallas | `postman/` (ver [Pruebas_postman.md](Pruebas_postman.md)) | Benjamín Canales |
| Verificaciones manuales | Recorridos hechos en el navegador antes de cada entrega | (ver sección 3) | Benjamín Canales |

**Estado actual: 214 pruebas automáticas, todas pasan** (última ejecución completa: 14-11-2026, 1 min 43 s).

---

## 1. Pruebas en video

**Autor:** Joaquín Rohland

| Archivo | Ubicación | Qué muestra |
|---|---|---|
| `LoginRegistro.mp4` | `Videos de Prueba/` | Registro de usuarios e inicio de sesión |
| `2026-09-13 20-26-37.mp4` | `Fase 1/Evidencias Grupales/` | Grabación de la Fase 1 |

Ambos archivos son la misma grabación, guardada en dos carpetas. Los videos muestran el sistema desde el navegador y sirven como evidencia visual de su funcionamiento.

---

## 2. Pruebas automáticas

**Autor:** Benjamín Canales

### Qué son y para qué sirven
Son 214 pruebas escritas en Python que ejecutan el backend como si fueran usuarios reales (registrarse, publicar una solicitud, postular, chatear, reportar, etc.) y comprueban que la respuesta sea la correcta. Sirven para detectar errores al instante cada vez que se cambia el código, sin tener que probar todo a mano.

### Cómo se ejecutan
Con el entorno virtual activado, desde la carpeta del proyecto:

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas usan una **base de datos temporal en memoria** (SQLite). **Nunca tocan la base de datos real de Supabase**: el archivo `conftest.py` lo garantiza y detiene todo si por error apuntara a la base real. Tampoco llaman a servicios externos: la IA (Gemini), la página oficial de certificados y el reloj se simulan, así que las pruebas son rápidas, gratuitas y repetibles.

### Resumen por fase

| Fase | Tema | Archivos | Pruebas |
|---|---|---|---|
| Fase 1 | Base del sistema: roles, solicitudes, postulaciones y citas | `test_seguridad`, `test_admin`*, `test_estudiante`, `test_flujo`* | 5 + 1 + 7 + 21 = **34** |
| Fase 2 | Verificación de estudiantes y búsqueda con IA | `test_verificacion`, `test_verificacion_certificado`, `test_busqueda` | 33 + 31 + 46 = **110** |
| Fase 3 (Sprint 3) | Chat, moderación, panel de administración y pendientes | `test_chat`, `test_moderacion`, `test_admin_moderacion`, `test_pendientes_sprint3`, y ampliaciones de `test_flujo` y `test_admin` | 9 + 36 + 12 + 9 + 3 + 1 = **70** |
| | | **Total** | **214** |

\* `test_flujo.py` tiene hoy 24 pruebas (21 de la Fase 1 y 3 agregadas en la Fase 3) y `test_admin.py` tiene 2 (1 de la Fase 1 y 1 de la Fase 3).

`tests/conftest.py` no tiene pruebas propias: prepara la base temporal y los usuarios de prueba (paciente y estudiante ya registrados con sesión iniciada). `tests/casos_prueba.json` guarda las consultas de ejemplo con el procedimiento esperado para evaluar la búsqueda.

---

### Fase 1: base del sistema (34 pruebas)

**`test_seguridad.py` (5): roles y datos privados**
- Sin iniciar sesión, la API rechaza el acceso (401).
- Cada rol solo accede a lo suyo: un paciente no puede usar las funciones del estudiante, y al revés (403).
- El registro público no permite crear administradores.
- Los administradores no son accesibles para otros roles.
- Nunca se muestra el correo ni el RUT de otra persona, solo el nombre abreviado (por ejemplo, "Camila Soto M.").

**`test_admin.py` (1 de la Fase 1): verificación de estudiantes**
- El administrador lista a los estudiantes en verificación (los pacientes no aparecen).
- Puede cambiar el estado de un estudiante a "Activo".
- Un estado inválido se rechaza (422), y un usuario que no es estudiante no se puede verificar (404).

**`test_estudiante.py` (7): requerimientos y ramos**
- Declarar y listar requerimientos, con su tutor y cantidad.
- Campos obligatorios y validaciones: el tutor es obligatorio, el área debe existir, la cantidad mínima es 1.
- Cada estudiante ve solo lo suyo y no puede modificar lo de otro (404).
- Registrar avance y pasar a "Completado" al alcanzar la cantidad requerida.
- Editar y cancelar; un requerimiento completado no se puede cancelar.
- Filtrar por estado.
- Ramos: crear, editar y eliminar, y validar el horario (la hora de término debe ser posterior a la de inicio).

**`test_flujo.py` (21 de la Fase 1): el recorrido completo del sistema**
- Solicitudes: el paciente publica, el estudiante la ve como caso; la comuna se toma del perfil si no se envía; validaciones de descripción y área; cada paciente ve solo las suyas.
- Filtros de casos: por área, urgencia, comuna y texto; las urgentes aparecen primero.
- Postulaciones en ambos sentidos: el estudiante postula y el paciente acepta, o el paciente solicita y el estudiante acepta.
- Reglas: no se puede postular dos veces, no se responde la propia postulación, al aceptar una se rechazan las demás, y al rechazar o cancelar la solicitud vuelve a estar abierta.
- Cancelar una solicitud cancela sus postulaciones pendientes.
- Citas: solo se agenda sobre una postulación aceptada, no se permiten fechas pasadas, y el paciente solo puede cancelar.
- Completar el tratamiento: la solicitud queda "Completada", el requerimiento suma avance y las citas pasan a "Realizada".
- Resúmenes de cada portal y búsqueda de estudiantes con filtros.
- Compatibilidad con la tabla `solicitudes` del equipo: los estados guardados en la base respetan sus restricciones, y una solicitud creada por otra aplicación se puede gestionar normalmente.

---

### Fase 2: verificación de estudiantes y búsqueda con IA (110 pruebas)

**`test_verificacion.py` (33): RUT, registro y subida del certificado**
- RUT: se acepta con o sin puntos y guion, con dígito verificador K o 0, y se guarda en el formato **12.345.678-9**. Se rechazan los inválidos (dígito incorrecto, muy corto, letras, vacío) y los RUT de empresa (desde 50.000.000).
- Documento de extranjero (`EXT-…`) se acepta sin cambios.
- Duplicados: no se puede registrar dos veces el mismo RUT, ni siquiera si quedó guardado en otro formato (con puntos, con guion o solo dígitos).
- Un estudiante sin verificar puede ver casos pero no postular; un paciente no ve ni solicita estudiantes sin verificar, y los pacientes no pasan por la verificación.
- Subir certificado: pasa a "En verificación"; se aceptan PDF, PNG y JPG y se rechazan otros archivos; los pacientes no pueden subirlo.
- Rechazo con motivo y nueva subida; renovar el certificado no quita el acceso.
- Privacidad: solo el administrador puede descargar el certificado y nunca se expone al paciente.

**`test_verificacion_certificado.py` (31): verificación automática del certificado**
- Aprueba solo si todo coincide (RUT, nombre, "alumno regular", carrera Odontología y semestre vigente); rechaza con motivo si falla cualquiera de esos puntos.
- El nombre se compara sin importar tildes ni orden; si el nombre es distinto o los datos son ilegibles, pasa a **revisión manual**.
- Lectura del QR y de la página oficial de verificación; sin QR legible queda para revisión manual.
- Seguridad (SSRF): solo se acepta el dominio oficial de la universidad; se rechazan direcciones locales, dominios que lo imitan, rutas manipuladas y textos que no son URL. La dirección se reconstruye siempre con el dominio fijo.
- Flujo completo: certificado válido activa al estudiante; certificado de otra persona se rechaza.
- Vigencia: el certificado vence al final del semestre, con 7 días de gracia (se prueban varias fechas de emisión y los bordes de la gracia). La aprobación manual del administrador, sin certificado, no vence.

**`test_busqueda.py` (46): búsqueda semántica con IA y matching**
- Catálogo de tratamientos: el real es válido y se rechazan catálogos con errores.
- Coincidencia: mejor frase encontrada, umbral, niveles (alta, media, sin coincidencia) y qué le explica el sistema al paciente en cada caso.
- Urgencia: detecta señales de alarma (hinchazón con fiebre, pus, sangrado que no para, golpe, dolor insoportable) y **no** marca urgencia en consultas comunes.
- Puntaje de coincidencia: procedimiento (50 %), ubicación (30 %) y disponibilidad (20 %), orden final y motivos de la coincidencia.
- **Ubicación por cercanía de comunas:** misma comuna 1,0; vecina 0,6; a dos comunas 0,4; más lejos o desconocida 0,3, que es el mínimo (nunca baja de ahí); si falta el dato, el puntaje es neutro.
- Disponibilidad: interpretación del texto del paciente y puntaje.
- Resultados: solo estudiantes verificados con cupo en el área, ordenados por puntaje y paginados de a diez; solo los pacientes pueden consultar.
- Fallas y límites: si la API de IA falla responde 503 sin filtrar el texto; límite de consultas por minuto (también con reloj simulado).
- Opiniones: se guardan sin texto ni usuario; se validan; las estadísticas son solo para el administrador.
- Caché del índice de IA: se usa sin llamar a la API; en Vercel sin caché o con caché desactualizado falla con un mensaje claro y no intenta reconstruirse; un disco de solo lectura no rompe la búsqueda.

---

### Fase 3 (Sprint 3): chat, moderación, administración y pendientes (70 pruebas)

**`test_chat.py` (9): chat entre paciente y estudiante**
- No hay chat hasta que la postulación se acepta.
- Conversación con mensajes no leídos y "visto".
- Solo los dos participantes acceden a la conversación.
- Validaciones del mensaje (vacío o demasiado largo).
- Al cancelar el vínculo o completar el tratamiento, el chat queda en solo lectura y avisa cuándo se borrará.
- El historial se borra a los 30 días del cierre; una conversación abierta nunca se borra.

**`test_moderacion.py` (36): moderación del chat con IA (Épica 5)**
- Reglas locales: dejan pasar mensajes normales (incluidos términos clínicos como "extracción" o "sangrado"); detectan insultos, amenazas (con variantes como letras repetidas o separadas por puntos) e insinuaciones.
- Mensajes fuera de tema se avisan pero **no suman** advertencia.
- IA (Gemini simulada): se interpreta su respuesta; si no hay clave, está apagada o falla, el mensaje pasa (no se bloquea por error); se usa solo cuando las reglas no deciden.
- Un mensaje bloqueado no le llega a la otra persona y la otra persona recibe una sola vez el recordatorio de que puede reportar.
- **3 advertencias en 30 días banean la cuenta** y crean un reporte automático; las advertencias vencen a los 30 días.
- El baneo cancela postulaciones y citas, avisa a la contraparte y, si es un paciente, cierra sus solicitudes.
- Reporte manual: se habilita tras unos mensajes, el motivo es obligatorio.
- Estado del chat: el chat detenido se muestra aunque no tenga mensajes; un chat cerrado normalmente no dice que fue por moderación; los chats son solo de quienes participan.

**`test_admin_moderacion.py` (12): panel de administración**
- Solo el administrador entra a la moderación.
- Bandeja: los reportes automáticos van primero y el detalle trae la evidencia.
- Resumen de moderación.
- Decisiones: banear desde un reporte; suspensión (time-out) que exige días y se levanta sola, y que deja las advertencias en cero.
- Descartar un baneo automático reactiva la cuenta y avisa a ambas personas; descartar un reporte de persona no toca la cuenta.
- Un reporte ya resuelto no se resuelve dos veces.
- Listado de cuentas y levantamiento de sanciones.
- La página `/admin` se sirve y el administrador inicia sesión; el registro público sigue sin crear administradores.

**`test_pendientes_sprint3.py` (9): archivado y edición de solicitudes**
- La descripción de la solicitud tiene un máximo de 500 caracteres.
- Se puede editar la clasificación de una solicitud abierta.
- Archivar deja el chat en solo lectura para las dos personas, sin cambiar la postulación ni las citas.
- Solo quien archivó puede reabrir; validaciones de archivar y reabrir.
- El chat archivado aparece en la lista aunque no tenga mensajes; el historial archivado se borra a los 30 días.
- Se puede reportar una conversación archivada.

**Ampliaciones de pruebas anteriores**
- `test_admin.py` (+1): el administrador ve, junto a la solicitud de un estudiante, sus datos y el estado de su certificado (fecha, tipo, revisión y motivo) para aceptar o rechazar.
- `test_flujo.py` (+3): eliminar datos que ya no se usan: un requerimiento solo se elimina si está cancelado; el paciente elimina una cita cancelada pero no una agendada; el paciente elimina una solicitud solo si está cancelada.

---

### Relación con el Definition of Done
Las pruebas automáticas respaldan, entre otros, estos criterios del DoD: códigos HTTP correctos (201, 400, 401, 403, 404, 409, 422, 503), separación de roles, no exposición de datos sensibles (correo, RUT y certificados), validación de campos obligatorios, estados de postulaciones, solicitudes y citas, y manejo de fallas de servicios externos.

---

## 3. Verificaciones manuales (Sprint 3)

Antes de subir los cambios del Sprint 3 a Vercel se hizo un recorrido en el navegador contra un servidor local con base temporal, para comprobar lo que las pruebas automáticas no cubren (la pantalla y el JavaScript):

| Qué se revisó | Resultado |
|---|---|
| Carga de todas las páginas (inicio, registro, ingreso, portales y `/admin`) y de sus archivos CSS/JS | Sin errores en la consola |
| Registro de estudiante con certificado adjunto (PDF), con el RUT formateándose al escribir | Correcto |
| Los tres roles (paciente, estudiante, administrador) inician sesión y ven su portal | Correcto |
| Panel de administración: Resumen, Reportes, Verificaciones y Cuentas | Correcto |
| Pantalla "Revisar solicitud": datos del estudiante junto al documento, con aprobar y rechazar | Correcto (el PDF se abre en pestaña nueva porque el visor del navegador integrado no lo muestra) |
| Revisión de mayúsculas/minúsculas en las rutas de archivos del frontend (Vercel distingue, Windows no) | Sin referencias con problema |
| Despliegue en Vercel con las variables de entorno configuradas | Confirmado por el equipo |

Los certificados usados para estas pruebas se probaron solo en una base temporal local y se eliminaron después.

---

## 4. Herramienta de apoyo

`scripts/crear_admin.py` crea un usuario administrador, porque el registro público no lo permite:

```bash
python -m scripts.crear_admin
```

---

## 5. Cómo agregar una prueba nueva
1. Crear o abrir un archivo `tests/test_<tema>.py`.
2. Escribir una función que empiece con `test_`.
3. Usar los usuarios de prueba listos de `conftest.py` pidiéndolos como parámetro (`paciente`, `estudiante`, `paciente2`, `estudiante2`, `client`).
4. Ejecutar `pytest` y confirmar que pasa.
5. Registrarla en este documento, en la fase que corresponda.
