from database import engine, Base
import models

print("Iniciando creacion de base de datos...")
Base.metadata.create_all(bind=engine)
print("Base de datos creada con exito")