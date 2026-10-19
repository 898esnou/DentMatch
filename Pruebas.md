# Pruebas de DentMatch

Este documento describe todas las pruebas del proyecto: qué hace cada una, qué demuestra, quién la realizó y dónde está guardada. A medida que se agreguen funcionalidades al proyecto, se irán sumando nuevas pruebas y este documento se actualizará.

El proyecto tiene dos tipos de pruebas:

| Tipo | Qué es | Dónde está | Autor |
|---|---|---|---|
| Pruebas en video | Grabaciones del sistema funcionando | `Videos de Prueba/` y `Fase 1/Evidencias Grupales/` | Joaquín Rohland |
| Pruebas automáticas | Código que verifica solo que el backend se comporte bien | `tests/` | Benjamín Canales |

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
Son 34 pruebas escritas en Python que ejecutan el backend como si fueran usuarios reales (registrarse, publicar una solicitud, postular, agendar una cita, etc.) y comprueban que la respuesta sea la correcta. Sirven para detectar errores al instante cada vez que se cambia el código, sin tener que probar todo a mano.

### Cómo se ejecutan
Con el entorno virtual activado, desde la carpeta del proyecto:

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas usan una **base de datos temporal en memoria** (SQLite). **Nunca tocan la base de datos real de Supabase**: el archivo `conftest.py` lo garantiza y detiene todo si por error apuntara a la base real.

### Dónde están

| Archivo | Pruebas | Qué demuestra |
|---|---|---|
| `tests/conftest.py` | (preparación) | Crea la base temporal y usuarios de prueba (paciente y estudiante ya registrados con sesión iniciada) |
| `tests/test_seguridad.py` | 5 | Control de acceso y protección de datos privados |
| `tests/test_admin.py` | 1 | Verificación de estudiantes por el administrador |
| `tests/test_estudiante.py` | 7 | Requerimientos y ramos del estudiante |
| `tests/test_flujo.py` | 21 | Solicitudes, postulaciones, citas y resúmenes |

### Qué verifica cada archivo

**`test_seguridad.py`: roles y datos privados**
- Sin iniciar sesión, la API rechaza el acceso (401).
- Cada rol solo accede a lo suyo: un paciente no puede usar las funciones del estudiante, y al revés (403).
- El registro público no permite crear administradores.
- Los administradores no son accesibles para otros roles.
- Nunca se muestra el correo ni el RUT de otra persona, solo el nombre abreviado (por ejemplo, "Camila Soto M.").

**`test_admin.py`: verificación de estudiantes**
- El administrador lista a los estudiantes en verificación (los pacientes no aparecen).
- Puede cambiar el estado de un estudiante a "Activo".
- Un estado inválido se rechaza (422), y un usuario que no es estudiante no se puede verificar (404).

**`test_estudiante.py`: requerimientos y ramos**
- Declarar y listar requerimientos, con su tutor y cantidad.
- Campos obligatorios y validaciones: el tutor es obligatorio, el área debe existir, la cantidad mínima es 1.
- Cada estudiante ve solo lo suyo y no puede modificar lo de otro (404).
- Registrar avance y pasar a "Completado" al alcanzar la cantidad requerida.
- Editar y cancelar; un requerimiento completado no se puede cancelar.
- Filtrar por estado.
- Ramos: crear, editar y eliminar, y validar el horario (la hora de término debe ser posterior a la de inicio).

**`test_flujo.py`: el recorrido completo del sistema**
- Solicitudes: el paciente publica, el estudiante la ve como caso; la comuna se toma del perfil si no se envía; validaciones de descripción y área; cada paciente ve solo las suyas.
- Filtros de casos: por área, urgencia, comuna y texto; las urgentes aparecen primero.
- Postulaciones en ambos sentidos: el estudiante postula y el paciente acepta, o el paciente solicita y el estudiante acepta.
- Reglas: no se puede postular dos veces, no se responde la propia postulación, al aceptar una se rechazan las demás, y al rechazar o cancelar la solicitud vuelve a estar abierta.
- Cancelar una solicitud cancela sus postulaciones pendientes.
- Citas: solo se agenda sobre una postulación aceptada, no se permiten fechas pasadas, y el paciente solo puede cancelar.
- Completar el tratamiento: la solicitud queda "Completada", el requerimiento suma avance y las citas pasan a "Realizada".
- Resúmenes de cada portal y búsqueda de estudiantes con filtros.
- Compatibilidad con la tabla `solicitudes` del equipo: los estados guardados en la base respetan sus restricciones, y una solicitud creada por otra aplicación se puede gestionar normalmente.

### Relación con el Definition of Done
Las pruebas automáticas respaldan, entre otros, estos criterios del DoD: códigos HTTP correctos (201, 400, 401, 403, 404, 409, 422), separación de roles, no exposición de datos sensibles, validación de campos obligatorios y estados de postulaciones, solicitudes y citas.

---

## 3. Herramienta de apoyo

`scripts/crear_admin.py` crea un usuario administrador, porque el registro público no lo permite:

```bash
python -m scripts.crear_admin
```

---

## 4. Cómo agregar una prueba nueva
1. Crear o abrir un archivo `tests/test_<tema>.py`.
2. Escribir una función que empiece con `test_`.
3. Usar los usuarios de prueba listos de `conftest.py` pidiéndolos como parámetro (`paciente`, `estudiante`, `paciente2`, `estudiante2`, `client`).
4. Ejecutar `pytest` y confirmar que pasa.
5. Registrarla en este documento.
