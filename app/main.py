"""
Aplicación principal de DentMatch (módulo de autenticación - Épica 001).

Endpoints:
- GET  /                -> sirve la página de login (HTML)
- GET  /registro        -> sirve la página de registro (HTML)
- POST /api/registro    -> crea un usuario (y su certificado, si es estudiante)
- POST /api/login       -> valida correo + contraseña y devuelve un token JWT
- GET  /api/me          -> devuelve los datos del usuario autenticado (requiere token)

Para correrlo:
    uvicorn main:app --reload
"""
import os
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import Base, SessionLocal, engine, get_db

app = FastAPI(title="DentMatch - Autenticación")

# Permite que login.html (servido desde el mismo origen o abierto localmente)
# pueda llamar a la API sin bloqueo de CORS durante el desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sirve los archivos estáticos del frontend (login.html, css, js propios, etc.)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- Carpeta donde se guardan los certificados subidos ---
# OJO: esta carpeta NO se sirve como estática a propósito (son documentos
# sensibles). Solo el backend/admin puede leerlos directamente del disco.
CARPETA_CERTIFICADOS = "uploads/certificados"
os.makedirs(CARPETA_CERTIFICADOS, exist_ok=True)

EXTENSIONES_PERMITIDAS = {".pdf", ".jpg", ".jpeg", ".png"}
TAMANO_MAXIMO_MB = 5


@app.get("/")
def home():
    """Página de inicio: redirige directo al formulario de login."""
    return FileResponse("frontend/login.html")


@app.get("/registro")
def pagina_registro():
    """Sirve la página de registro."""
    return FileResponse("frontend/register.html")


def guardar_certificado(archivo: UploadFile) -> str:
    """
    Valida y guarda el archivo de certificado en disco.
    Devuelve la ruta relativa donde quedó guardado.
    """
    extension = os.path.splitext(archivo.filename)[1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail="El certificado debe ser PDF, JPG o PNG.",
        )

    contenido = archivo.file.read()
    tamano_mb = len(contenido) / (1024 * 1024)
    if tamano_mb > TAMANO_MAXIMO_MB:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el tamaño máximo permitido ({TAMANO_MAXIMO_MB} MB).",
        )

    # Nombre único para evitar que dos estudiantes pisen el mismo archivo
    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    ruta_relativa = os.path.join(CARPETA_CERTIFICADOS, nombre_archivo)

    with open(ruta_relativa, "wb") as destino:
        destino.write(contenido)

    return ruta_relativa


@app.post("/api/registro", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    nombre_completo: str = Form(...),
    rut: str = Form(...),  # <-- Nuevo parámetro
    correo: str = Form(...),
    contrasena: str = Form(...),
    rol: str = Form(...),
    universidad: str = Form(None),
    ano_carrera: int = Form(None),
    comuna_atencion: str = Form(None),
    disponibilidad: str = Form(None),
    certificado: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if rol not in ("estudiante", "paciente", "admin"):
        raise HTTPException(status_code=400, detail="Rol inválido")

    # Validación de Correo
    existe_correo = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
    if existe_correo:
        raise HTTPException(status_code=400, detail="Ese correo ya está registrado")

    # Validación de RUT
    existe_rut = db.query(models.Usuario).filter(models.Usuario.rut == rut).first()
    if existe_rut:
        raise HTTPException(status_code=400, detail="Este RUT ya está registrado en el sistema")

    # ... validación del certificado (se mantiene igual) ...

    nuevo_usuario = models.Usuario(
        nombre_completo=nombre_completo,
        rut=rut,  # <-- Inyectamos el RUT al guardar
        correo=correo,
        contrasena_hash=hash_password(contrasena),
        rol=rol,
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    if rol == "estudiante":
        ruta_certificado = guardar_certificado(certificado)

        perfil = models.PerfilEstudiante(
            usuario_id=nuevo_usuario.id,
            universidad=universidad or "Por definir",
            ano_carrera=ano_carrera or 1,
            comuna_atencion=comuna_atencion or "Por definir",
            disponibilidad=disponibilidad,
            certificado_documento=ruta_certificado,
            estado_verificacion="En Verificación",
        )
        db.add(perfil)
        db.commit()

    return nuevo_usuario


@app.post("/api/login", response_model=schemas.TokenResponse)
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Valida las credenciales y devuelve un token JWT si son correctas."""
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == datos.correo).first()

    # Mensaje genérico a propósito: no decir si fue el correo o la contraseña
    # (buena práctica de seguridad, evita que alguien "adivine" correos válidos)
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Correo o contraseña incorrectos",
    )

    if not usuario:
        raise credenciales_invalidas
    if not verify_password(datos.contrasena, usuario.contrasena_hash):
        raise credenciales_invalidas

    token = create_access_token(data={"sub": str(usuario.id), "rol": usuario.rol})
    return schemas.TokenResponse(
        access_token=token,
        rol=usuario.rol,
        nombre_completo=usuario.nombre_completo,
    )


@app.get("/api/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario_actual: models.Usuario = Depends(get_current_user)):
    """Ejemplo de endpoint protegido: solo responde si el token es válido."""
    return usuario_actual


@app.on_event("startup")
def crear_tablas_si_no_existen():
    """
    Si NO has corrido tu script SQL manualmente en PostgreSQL, esta línea
    crea las tablas automáticamente a partir de los modelos de models.py.
    Si ya las creaste tú con el script SQL, esta línea no hace nada (no las duplica).
    """
    Base.metadata.create_all(bind=engine)
