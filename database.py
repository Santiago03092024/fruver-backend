import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. URL de la base de datos (Usa local si no detecta la de Render)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fruver.db")

# 2. Corrección para Render/Postgres
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Configuración del Motor
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # Mantenemos solo lo esencial para que Supabase no te de error de conexión
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"sslmode": "require"},
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

