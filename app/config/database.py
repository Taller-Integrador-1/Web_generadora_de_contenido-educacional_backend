import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import dotenv

dotenv.load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Falta la variable de entorno DATABASE_URL para la conexión de base de datos.")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()