from app import app, db, User

def crear_supervisores():
    with app.app_context():
        # Lista de áreas (puedes cambiar estos nombres por los reales de tu planta)
        areas = [
            "Producción A", "Producción B", "Mantenimiento", "Calidad", 
            "Logística", "Embarques", "Sanidad", "Seguridad", 
            "Almacén", "Talleres", "Servicios", "Planta de Agua",
            "Recursos Humanos", "Finanzas", "Proyectos", "Sistemas",
            "Laboratorio", "Intendencia"
        ]

        print("--- Iniciando creación de supervisores ---")
        
        for i, nombre_area in enumerate(areas, start=1):
            # Creamos un usuario tipo: supervisor1, supervisor2...
            usuario = f"sup{i}" 
            
            # Verificamos si ya existe para no duplicar
            user_exists = User.query.filter_by(username=usuario).first()
            
            if not user_exists:
                nuevo_sup = User(
                    username=usuario,
                    password="123", # Contraseña inicial para todos
                    role="supervisor",
                    area=nombre_area
                )
                db.session.add(nuevo_sup)
                print(f"✅ Creado: {usuario} para el área {nombre_area}")
            else:
                print(f"⚠️ El usuario {usuario} ya existe, saltando...")

        db.session.commit()
        print("------------------------------------------")
        print("¡PROCESO TERMINADO!")
        print("Todos los supervisores entrarán con su usuario (sup1, sup2...) y pass: 123")

if __name__ == '__main__':
    crear_supervisores()