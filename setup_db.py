import os
from app import app, db
from models import User

def inicializar_todo():
    # Buscamos la ruta absoluta para que no haya pierde
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'database.db')

    # Si ya existe un archivo viejo, lo borramos para que sea una instalación limpia
    if os.path.exists(db_path):
        os.remove(db_path)
        print("--- Eliminando base de datos antigua ---")

    with app.app_context():
        print("--- Creando archivo database.db y tablas ---")
        # ESTA ES LA LÍNEA MÁGICA: Crea el archivo y las tablas
        db.create_all()

        # Creamos al Administrador
        print("--- Registrando usuario administrador ---")
        admin = User(
            username='admin', 
            password='123', 
            role='admin', 
            area='Seguridad/Sistemas'
        )
        
        # Creamos un Supervisor de ejemplo (puedes crear los 18 después)
        supervisor = User(
            username='sup1', 
            password='123', 
            role='supervisor', 
            area='Planta Sabinas'
        )

        db.session.add(admin)
        db.session.add(supervisor)
        db.session.commit()

        print("------------------------------------------")
        print("¡TODO LISTO!")
        print(f"Se ha creado el archivo en: {db_path}")
        print("Ya puedes entrar con:")
        print("Usuario: admin | Pass: 123")
        print("------------------------------------------")

if __name__ == '__main__':
    inicializar_todo()