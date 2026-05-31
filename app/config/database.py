import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import dotenv

dotenv.load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_mRywhSj0L3Mu@ep-bold-recipe-aqijn6c6-pooler.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()