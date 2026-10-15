"""
Rutas que sirven las páginas HTML. El index (/) es para visitantes; cada rol
tiene su portal (/paciente, /estudiante). La protección real (token + rol)
la hace la API.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)


def _pagina(ruta: str) -> FileResponse:
    # no-cache: el navegador revalida siempre y nunca muestra una versión vieja.
    return FileResponse(ruta, headers={"Cache-Control": "no-cache"})


@router.get("/")
def inicio():
    return _pagina("frontend/index.html")


@router.get("/login")
def login():
    return _pagina("frontend/login.html")


@router.get("/registro")
def registro():
    return _pagina("frontend/register.html")


@router.get("/paciente")
def portal_paciente():
    return _pagina("frontend/PortalPaciente.html")


@router.get("/estudiante")
def portal_estudiante():
    return _pagina("frontend/PortalEstudiante.html")
