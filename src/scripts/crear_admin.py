"""
Crea un usuario administrador (el registro público no permite el rol admin).

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python -m scripts.crear_admin

Te pregunta nombre, RUT, correo y contraseña. La contraseña no se muestra
al escribirla ni se guarda en ningún archivo.
"""
from getpass import getpass

from app import models
from app.auth import hash_password
from app.database import Base, SessionLocal, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    nombre = input("Nombre completo: ").strip()
    rut = input("RUT: ").strip()
    correo = input("Correo: ").strip()
    contrasena = getpass("Contraseña (mín. 6 caracteres): ")
    if len(contrasena) < 6 or not nombre or not rut or not correo:
        raise SystemExit("Todos los campos son obligatorios y la contraseña debe tener 6+ caracteres.")

    db = SessionLocal()
    try:
        if db.query(models.Usuario).filter(
            (models.Usuario.correo == correo) | (models.Usuario.rut == rut)
        ).first():
            raise SystemExit("Ya existe un usuario con ese correo o RUT.")
        db.add(models.Usuario(
            nombre_completo=nombre, rut=rut, correo=correo,
            contrasena_hash=hash_password(contrasena), rol="admin",
        ))
        db.commit()
        print(f"Administrador {correo} creado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
