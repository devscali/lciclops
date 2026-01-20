"""
CICLOPS - Configuracion de PostgreSQL
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Railway provee DATABASE_URL automaticamente cuando agregas Postgres
DATABASE_URL = os.getenv("DATABASE_URL")

# Si no hay DATABASE_URL, usar SQLite local para desarrollo
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./ciclops_dev.db"
    print("⚠️ Usando SQLite local (desarrollo)")
else:
    # Railway usa postgres:// pero SQLAlchemy necesita postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print("✅ Conectado a PostgreSQL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False  # Cambiar a True para debug SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency para obtener sesion de DB"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
