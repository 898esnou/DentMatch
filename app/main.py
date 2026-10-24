"""
Aplicación de DentMatch (prototipo personal de Benjamín).

Se conecta a la MISMA base de datos de Supabase que el backend del equipo,
pero corre en su propio servidor local (puerto 8001).

Estructura:
- app/routers/auth.py     -> registro, login, /api/me
- app/routers/perfil.py   -> perfil de estudiante / paciente
- app/routers/paginas.py  -> páginas HTML (/, /login, /registro, /paciente, /estudiante)
- app/routers/ramos.py, requerimientos.py  -> el estudiante declara sus ramos y requerimientos
- app/routers/solicitudes.py, casos.py, estudiantes.py -> solicitudes del paciente y cómo se ven
- app/routers/postulaciones.py, citas.py   -> el vínculo paciente<->estudiante y su agenda
- app/routers/verificacion.py -> el estudiante sube su certificado de alumno regular
- app/routers/resumen.py, catalogos.py, admin.py
La documentación interactiva de toda la API queda en /docs.

Para correrlo:
    uvicorn app.main:app --reload --port 8001
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import (
    admin, auth, casos, catalogos, citas, estudiantes, paginas, perfil, postulaciones,
    ramos, requerimientos, resumen, solicitudes, verificacion,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas que falten (las existentes en Supabase no se tocan).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="DentMatch (prototipo Benjamín)", lifespan=lifespan)

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
    postulaciones, citas, resumen, admin, verificacion,
):
    app.include_router(modulo.router)
