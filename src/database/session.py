import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config.settings import settings


DATABASE_URL = settings.DATABASE_URL or os.getenv("DATABASE_URL") or "sqlite:///./dev.db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
