"""
Aplicación de DentMatch (Proyecto Capstone, Grupo Ockham).

Backend FastAPI que se conecta a la base de datos PostgreSQL del equipo en Supabase
y sirve también el frontend (carpeta frontend/, montada en /static).

Estructura (app/routers/):
- paginas.py                        páginas HTML (/, /login, /registro, /paciente, /estudiante, /admin)
- auth.py, perfil.py                registro, login, /api/me y el perfil de cada rol
- ramos.py, requerimientos.py       el estudiante declara sus clínicas y sus requerimientos
- solicitudes.py, casos.py,         lo que publica el paciente y cómo lo ve el estudiante;
  estudiantes.py, busqueda.py       los estudiantes que ve el paciente y la búsqueda semántica
- postulaciones.py                  el vínculo paciente <-> estudiante
- chat.py, avisos.py                chat de coordinación (fecha, hora y lugar se acuerdan aquí)
- verificacion.py                   el estudiante sube su certificado de alumno regular
- admin.py, admin_moderacion.py     panel de administración (verificaciones, reportes, cuentas)
- resumen.py, catalogos.py          números de la cabecera y valores fijos
No hay agenda de citas: el día y la hora se coordinan solo por el chat.
La documentación interactiva de toda la API queda en /docs.

Para correrlo (desde la carpeta del proyecto, porque el frontend se sirve con una ruta relativa):
    uvicorn app.main:app --reload --port 8001
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import (
    admin, admin_moderacion, auth, avisos, busqueda, casos, catalogos, chat, estudiantes, paginas,
    perfil, postulaciones, ramos, requerimientos, resumen, solicitudes, verificacion,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas que falten (las existentes en Supabase no se tocan).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="DentMatch", lifespan=lifespan)

# El frontend se sirve desde el mismo origen; solo permitimos orígenes locales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8001", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StaticSinCache(StaticFiles):
    """Sirve el frontend pidiendo al navegador que revalide en cada carga,
    para que nunca use una versión vieja de un CSS/JS cacheado."""

    async def get_response(self, path, scope):
        respuesta = await super().get_response(path, scope)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


app.mount("/static", StaticSinCache(directory="frontend"), name="static")

app.include_router(paginas.router)
app.include_router(auth.router)
app.include_router(perfil.router)
for modulo in (
    catalogos, ramos, requerimientos, solicitudes, casos, estudiantes,
    postulaciones, chat, resumen, admin, admin_moderacion, verificacion, busqueda, avisos,
):
    app.include_router(modulo.router)
