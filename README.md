# DentMatch
Proyecto Capstone Grupo Ockham

## Descripción
DentMatch es una plataforma web que conecta a estudiantes de Odontología que necesitan pacientes para sus prácticas clínicas con personas que buscan atención dental de bajo costo. Los estudiantes crean un perfil verificado con sus procedimientos pendientes, su disponibilidad y su lugar de atención. Los pacientes publican su necesidad y encuentran estudiantes que se ajusten a ella. La plataforma gestiona las postulaciones entre ambas partes y la agenda de citas, mostrando información que genera confianza (universidad, año de carrera, supervisión docente).

El **puntaje de coincidencia** (0 a 100) combina el procedimiento que necesita el paciente (50 %), la ubicación (30 %) y la disponibilidad (20 %). La ubicación premia la misma comuna y baja según cuántas comunas separan al paciente del estudiante, con un mínimo de 0,3 (ver `app/comunas.py`).

Además incluye una búsqueda con IA que relaciona lo que escribe el paciente con procedimientos odontológicos, un puntaje de coincidencia entre pacientes y estudiantes, un chat de coordinación moderado automáticamente (reglas y IA), reportes de conducta y un panel de administración.

## Integrantes
- Benjamín Canales, Líder del Proyecto y Desarrollador Backend
- Jorge Curiqueo, Desarrollo IA y Datos
- Joaquín Rohland, Desarrollador Frontend y Desarrollo IA

## Tecnologías
- **Backend:** Python con FastAPI y SQLAlchemy
- **Frontend:** HTML, CSS y JavaScript (lo sirve el mismo backend)
- **Base de datos:** PostgreSQL (Supabase)
- **Autenticación:** tokens JWT y contraseñas con hash bcrypt
- **IA:** Gemini (Google) para la búsqueda de procedimientos y la moderación del chat

## Aviso sobre datos y uso de IA
DentMatch es un **proyecto académico** (Capstone). No está pensado para usuarios ni datos reales: usa solo cuentas y mensajes de prueba.

- **Búsqueda con IA:** el texto que escribe el paciente en la búsqueda se envía a la API de Gemini (Google) para relacionarlo con un procedimiento del catálogo. No es un diagnóstico.
- **Moderación del chat:** los mensajes se revisan antes de enviarse con reglas locales y, si hace falta, con Gemini. Los mensajes bloqueados se guardan como evidencia para el administrador. Si el servicio de IA no responde, el mensaje se envía y solo se aplican las reglas locales.
- **Aviso de urgencia:** se detecta con reglas en el propio servidor; ese texto no se envía a ningún servicio externo.
- **Certificado de alumno regular:** el estudiante lo adjunta al registrarse. Se guarda en un almacenamiento privado y solo lo abre el administrador, que lo revisa junto a los datos de la solicitud. El sistema intenta validarlo solo leyendo su código QR.
- **Conservación:** el historial de un chat cerrado, archivado o detenido se elimina solo a los 30 días.

## Requisitos previos
- Python 3.10 o superior
- Git
- Acceso a una base de datos PostgreSQL (la del equipo en Supabase o una local)

## Puesta en marcha

### 1. Obtener el código
```bash
git clone <URL-del-repositorio>
cd DentMatch
```

### 2. Crear y activar el entorno virtual
```bash
python -m venv venv
```

Activarlo según tu sistema:

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `.\venv\Scripts\Activate.ps1` |
| Windows (CMD) | `venv\Scripts\activate.bat` |
| macOS / Linux | `source venv/bin/activate` |

Sabrás que funcionó cuando el inicio de la línea muestre `(venv)`.

> En PowerShell, si aparece un error de permisos, ejecuta una vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> y vuelve a activar el entorno.

### 3. Instalar las dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar las variables de entorno
Copia el archivo de ejemplo con el nombre `.env` (sin `.example`):

```bash
# Windows (PowerShell)
Copy-Item .env.example .env
# macOS / Linux
cp .env.example .env
```

Luego edita `.env` y completa dos valores:

| Variable | Qué es |
|---|---|
| `DATABASE_URL` | Dirección de conexión a PostgreSQL. Pídele la del equipo a quien administra la base de datos, o usa una local con el formato `postgresql://usuario:contraseña@localhost:5432/dentmatch`. |
| `SECRET_KEY` | Clave con la que el servidor firma los tokens de sesión. Puede ser cualquier texto largo y aleatorio. |

Para generar una `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> El archivo `.env` contiene secretos. **Nunca debe subirse a Git** (ya está en el `.gitignore`).

### 5. Iniciar el servidor
```bash
uvicorn app.main:app --reload --port 8001
```

Al arrancar, la aplicación crea automáticamente las tablas que falten en la base de datos. Las que ya existen no se modifican.

Si todo salió bien verás:
```
INFO:     Uvicorn running on http://127.0.0.1:8001
INFO:     Application startup complete.
```

### 6. Abrir la aplicación

| Dirección | Qué es |
|---|---|
| http://127.0.0.1:8001/ | Página principal |
| http://127.0.0.1:8001/login | Inicio de sesión |
| http://127.0.0.1:8001/registro | Registro de estudiantes y pacientes |
| http://127.0.0.1:8001/docs | Documentación interactiva de la API (Swagger) |
> **Nota:** estas direcciones corresponden al entorno de desarrollo local: el servidor (Uvicorn) corre en tu propio computador (`localhost`), por lo que solo tú puedes acceder a ellas. La versión publicada está en Vercel: https://dent-match-eta.vercel.app (ver la sección *Despliegue en Vercel*).

Después de iniciar sesión, cada usuario entra a su portal: `/paciente` o `/estudiante`.

> Usa siempre el puerto **8001**: el servidor solo acepta peticiones de ese origen.

## Tareas habituales

### Crear un usuario administrador
El registro público no permite crear administradores. Para crear uno:
```bash
python -m scripts.crear_admin
```
Te pedirá nombre, RUT, correo y contraseña.

Para entrar, ve a `/login` y pulsa **Acceso administración** (o abre `/login?rol=admin`). El panel está en `/admin` y tiene:
- **Reportes:** bandeja de moderación del chat. Cada reporte muestra la evidencia (mensajes bloqueados por la IA y la conversación) y permite mantener el baneo, dar un time-out o descartarlo.
- **Verificaciones:** revisar cada solicitud con los datos del estudiante (nombre, RUT, universidad, año) y su certificado de alumno regular lado a lado, y aprobarla o rechazarla con un motivo.
- **Cuentas:** buscar personas, ver su estado y levantar una sanción.
- **Resumen:** números de la moderación.

### Formato del RUT
En el registro el RUT se escribe solo con números y el dígito verificador: los puntos y el guion se agregan automáticamente y se guarda como `12.345.678-9`.

### Ejecutar las pruebas automáticas
```bash
pip install -r requirements-dev.txt
pytest
```
Las pruebas usan una base de datos temporal en memoria: **no tocan** la base real.

### Detener el servidor
Presiona `Ctrl + C` en la terminal. Para salir del entorno virtual, escribe `deactivate`.

## Despliegue en Vercel
La aplicación se publica desde la rama `main`: cada `git push` genera un despliegue nuevo. En **Settings → Environment Variables** del proyecto deben estar:

| Variable | Para qué |
|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL (usar el *pooler* de Supabase, puerto 6543) |
| `SECRET_KEY` | Firma de los tokens de sesión |
| `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` | Almacenamiento de los certificados (bucket **privado** `certificados`) |
| `GEMINI_API_KEY` | Búsqueda con IA |
| `GEMINI_API_KEY_MODERACION` | Moderación del chat (opcional; si falta se usa la anterior o solo las reglas) |

Importante: en Vercel el índice de la búsqueda no se puede construir, así que `app/datos/embeddings_cache.npz` debe viajar en el repositorio junto con `app/datos/procedimientos.json`. Si se cambia el catálogo, hay que regenerarlo con `python -m scripts.construir_cache` y subir ambos archivos.

## Estructura del proyecto
```
app/            Backend (FastAPI)
  routers/      Un archivo por sección de la API (auth, solicitudes, postulaciones, citas, chat, admin...)
  models.py     Tablas de la base de datos
  matching.py   Puntaje de coincidencia (con comunas.py)
  moderacion.py, sanciones.py   Moderación del chat, advertencias, baneos y reportes
  auth.py       Contraseñas, tokens y control de acceso por rol
frontend/       Páginas, estilos y scripts del navegador
scripts/        Herramientas de apoyo (crear administrador, construir el índice de IA)
migraciones/    Scripts SQL para la base de datos (Supabase)
tests/          Pruebas automáticas
```

## Solución de problemas

| Problema | Posible causa |
|---|---|
| `No se encontró DATABASE_URL` o `SECRET_KEY` | Falta el archivo `.env` o alguna de las dos variables. |
| `ModuleNotFoundError` | El entorno virtual no está activado o faltó instalar las dependencias. |
| No conecta a la base de datos | `DATABASE_URL` incorrecta o sin acceso a internet (Supabase). |
| La página no carga o el login falla | Estás usando un puerto distinto de 8001. |
