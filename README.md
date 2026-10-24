# DentMatch - Prototipo de Benjamín (Login / Register)

Este es un proyecto **aislado** del repositorio oficial del equipo.
Se conecta a la **misma base de datos de Supabase**, pero corre en un
servidor local independiente (puerto **8001**, para no chocar con el
backend oficial que corre en el puerto 8000).

## Qué incluye

- Registro y login (estudiante / paciente) con sesión JWT y control por rol
- Portal del estudiante: requerimientos clínicos (con su tutor), ramos/clínicas,
  casos disponibles, postulaciones y citas
- Portal del paciente: publicar solicitudes, ver estudiantes, solicitar atención,
  responder candidatos y ver sus citas
- Administración: verificar estudiantes (`/api/admin/...`)
- Backend FastAPI. La documentación interactiva de toda la API está en `/docs`.

## Cómo funciona el flujo (backend)

1. El **paciente** publica una *solicitud* (qué necesita, área, urgencia, comuna).
2. Se vinculan por una *postulación*, que puede iniciar **cualquiera de los dos**:
   el estudiante "postula a un caso" o el paciente "solicita" a un estudiante.
   La **contraparte** la acepta o rechaza. Al aceptar, la solicitud queda *Asignada*
   y las demás postulaciones pendientes se rechazan.
3. El estudiante **agenda la cita** y, al terminar, marca el **tratamiento realizado**:
   la solicitud queda *Completada* y suma al **requerimiento** vinculado
   (que llega a *Completado* al alcanzar la cantidad requerida).

Tablas nuevas: `perfil_paciente`, `ramos_estudiante`, `requerimientos`, `solicitudes`,
`postulaciones`, `citas`. Se crean solas al arrancar el servidor y **no modifican** las
tablas existentes (`usuarios`, `perfil_estudiante`).

## Verificación de usuarios

- **Paciente:** el documento de identidad se valida al registrarse. Puede ser **RUT chileno**
  (con dígito verificador, módulo 11; se rechazan los RUT de empresa, desde 50.000.000) o **documento extranjero** (pasaporte u otro: 5 a 16
  letras/números; ahí solo se puede validar el formato). Si es válido, queda habilitado.
- **Estudiante:** nace **"No verificado"**. Desde su portal pulsa **"Verificar tu perfil"** y sube su
  certificado de alumno regular (PDF/JPG/PNG, máx. 5 MB). Estados: `No verificado` →
  `En Verificación` → `Activo` | `Rechazado` (con motivo; puede volver a subirlo). También puede
  renovarlo estando `Activo` sin perder el acceso.
- Sin verificar, el estudiante **puede ver los casos** de pacientes pero **no postular, responder,
  agendar ni publicar requerimientos** (lo exige el backend). Sus datos de perfil y ramos sí puede editarlos.
- Los pacientes **solo ven estudiantes verificados**.
- **Lectura automática del QR** (`app/verificacion_certificado.py`, certificados de la UNAB): se lee el QR,
  se consulta `certificados.unab.cl` (solo ese dominio) y, si el RUT coincide con la cuenta, es alumno regular
  de Odontología y el certificado es del semestre en curso, queda `Activo` solo. Si los datos no sirven se rechaza con
  motivo. Si no se puede decidir (sin QR legible, web de la UNAB caída, nombre distinto), queda
  `En Verificación` y lo resuelve un admin con
  `PATCH /api/admin/estudiantes/{id}/verificacion` (`{estado, motivo}`); puede ver el archivo con
  `GET /api/admin/estudiantes/{id}/certificado`.
- **Vigencia semestral** (`app/vigencia.py`): cuenta el mes y año de emisión. Emitido de enero a junio vale hasta
  el 30 de junio; de julio a diciembre, hasta el 31 de diciembre. Terminado el semestre hay **7 días de gracia**
  (aviso en la campana y en el banner) para subir uno nuevo; después vuelve a `No verificado`. Antes de usar
  esto contra Supabase ejecutar también `migraciones/002_vigencia_semestral.sql`.
- Los certificados van a un **bucket privado** de Supabase Storage (`certificados`). Para eso el `.env`
  necesita `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` (ver `.env.example`). Sin ellas, en desarrollo
  se guardan en la carpeta local `uploads/` (excluida de git).
- **Antes de usar esta versión contra Supabase hay que ejecutar** `migraciones/001_verificacion_estudiante.sql`
  en el SQL Editor (amplía el CHECK de estados, crea la tabla de certificados y el bucket).

## Para quien haga el matching con IA

El backend deja los datos listos, pero **no calcula compatibilidad**. Los puntos de enganche:

- `GET /api/casos` (lo que ve el estudiante) y `GET /api/estudiantes` (lo que ve el paciente)
  devuelven listas ordenadas de forma simple; ahí se puede ordenar/puntuar con IA y agregar
  un campo `compatibilidad` a `CasoOut` / `EstudianteOut` (`app/schemas_dominio.py`).
- Las áreas clínicas están en `app/catalogos.py` (`AREAS`): una solicitud trae su `area`
  elegida por el paciente; la IA puede reclasificarla.
- Cada estudiante expone sus `requerimientos_abiertos` (tratamiento, tutor, restantes) y
  sus `ramos`: son los datos para emparejar.
- Los portales ocultan el porcentaje mientras la API no lo envíe.

## Pendiente (a propósito, para más adelante)

- Matching con IA (ver sección anterior) y chat entre paciente y estudiante.
- Para crear un admin: `python -m scripts.crear_admin`.

## Instalación

### 1. Crear y activar el entorno virtual

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar el archivo `.env`

Copia `.env.example` como `.env` y completa `DATABASE_URL` con la
**misma cadena de conexión de Supabase** que ya usa el equipo
(pídesela a Jorge por el canal privado, nunca por chat).

### 4. Levantar el servidor

```bash
uvicorn app.main:app --reload --port 8001
```

### 5. Probar

Abre en el navegador:

- Login: http://127.0.0.1:8001/
- Registro: http://127.0.0.1:8001/registro
- Documentación de la API: http://127.0.0.1:8001/docs

## Tests

Corren contra SQLite en memoria (nunca tocan Supabase):

```bash
pip install -r requirements-dev.txt
pytest
```
