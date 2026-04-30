from app import app, db, User

def cargar_datos_reales():
    # Lista organizada según tu imagen: (Nombre, Área)
    supervisores = [
        # Producción
        ("Ronaldo", "Producción"), ("Leonardo", "Producción"), ("Sadib", "Producción"),
        ("Rosmal", "Producción"), ("David R", "Producción"), ("Jose T", "Producción"),
        ("Rodolfo", "Producción"), ("Reyes", "Producción"), ("Hector", "Producción"),
        # Mtto Pro
        ("Gilberto", "Mtto Pro"), ("Jose Lopez", "Mtto Pro"), ("Rene", "Mtto Pro"),
        # Otros
        ("Ramiro", "Mtto Ser"),
        ("Fco Ramirez", "Sanidad"),
        ("Ronald", "MP-REF"),
        ("Hilda", "Calidad"),
        ("Karina", "CH"),
        ("Alex", "CADI´S")
    ]

    with app.app_context():
        print("--- Limpiando usuarios antiguos (opcional) ---")
        # Borramos supervisores genéricos previos para no tener basura
        User.query.filter(User.role == 'supervisor').delete()
        
        print("--- Cargando supervisores de la imagen ---")
        for nombre, area in supervisores:
            # El usuario será el nombre (en minúsculas y sin espacios)
            user_login = nombre.lower().replace(" ", "")
            
            nuevo_usuario = User(
                username=user_login,
                password="123", # Contraseña inicial
                role="supervisor",
                area=area
            )
            db.session.add(nuevo_usuario)
            print(f"✅ Registrado: {nombre} | Área: {area} | Usuario: {user_login}")
        
        db.session.commit()
        print("\n¡Listo! Todos los supervisores han sido cargados con éxito.")

if __name__ == '__main__':
    cargar_datos_reales()