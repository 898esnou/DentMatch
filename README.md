# DentMatch
Proyecto Capstone Grupo Ockham

## Descripción
DentMatch es una plataforma web que conecta a estudiantes de Odontología que necesitan pacientes para sus prácticas clínicas con personas que buscan atención dental de bajo costo. Los estudiantes crean un perfil verificado con sus procedimientos pendientes, su disponibilidad y su lugar de atención. Los pacientes publican su necesidad y encuentran estudiantes que se ajusten a ella. La plataforma gestiona las postulaciones entre ambas partes y la agenda de citas, mostrando información que genera confianza (universidad, año de carrera, supervisión docente).

En etapas siguientes se incorporarán un sistema de coincidencia y clasificación de solicitudes con IA, un chat de coordinación y moderación de contenido.

## Integrantes
- Benjamín Canales, Líder del Proyecto y Desarrollador Backend
- Jorge Curiqueo, Desarrollo IA y Datos
- Joaquín Rohland, Desarrollador Frontend y Desarrollo IA

## Tecnologías
- **Backend:** Python con FastAPI y SQLAlchemy
- **Frontend:** HTML, CSS y JavaScript (lo sirve el mismo backend)
- **Base de datos:** PostgreSQL (Supabase)
- **Autenticación:** tokens JWT y contraseñas con hash bcrypt

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
> **Nota:** estas direcciones corresponden al entorno de desarrollo local: el servidor (Uvicorn) corre en tu propio computador (`localhost`), por lo que solo tú puedes acceder a ellas. Actualmente se están evaluando distintos servicios de alojamiento (hosting) para publicar la aplicación en internet, pero aún no hay uno definido. Esta sección se actualizará con la dirección pública cuando esté disponible.

Después de iniciar sesión, cada usuario entra a su portal: `/paciente` o `/estudiante`.

> Usa siempre el puerto **8001**: el servidor solo acepta peticiones de ese origen.

## Tareas habituales

### Crear un usuario administrador
El registro público no permite crear administradores. Para crear uno:
```bash
python -m scripts.crear_admin
```
Te pedirá nombre, RUT, correo y contraseña. El administrador puede verificar estudiantes mediante la API (`/docs`).

### Ejecutar las pruebas automáticas
```bash
pip install -r requirements-dev.txt
pytest
```
Las pruebas usan una base de datos temporal en memoria: **no tocan** la base real.

### Detener el servidor
Presiona `Ctrl + C` en la terminal. Para salir del entorno virtual, escribe `deactivate`.

## Estructura del proyecto
```
app/            Backend (FastAPI)
  routers/      Un archivo por sección de la API (auth, solicitudes, postulaciones, citas...)
  models.py     Tablas de la base de datos
  auth.py       Contraseñas, tokens y control de acceso por rol
frontend/       Páginas, estilos y scripts del navegador
scripts/        Herramientas de apoyo (crear administrador)
tests/          Pruebas automáticas
```

## Solución de problemas

| Problema | Posible causa |
|---|---|
| `No se encontró DATABASE_URL` o `SECRET_KEY` | Falta el archivo `.env` o alguna de las dos variables. |
| `ModuleNotFoundError` | El entorno virtual no está activado o faltó instalar las dependencias. |
| No conecta a la base de datos | `DATABASE_URL` incorrecta o sin acceso a internet (Supabase). |
| La página no carga o el login falla | Estás usando un puerto distinto de 8001. |
