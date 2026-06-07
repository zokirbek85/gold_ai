"""
Simple initialization script to create DB tables for Phase 1.
"""
from src.database.session import engine
from src.database.models import Base


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized")
