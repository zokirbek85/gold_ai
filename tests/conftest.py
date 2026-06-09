"""
Shared pytest fixtures for Gold AI test suite.
Uses SQLite in-memory database — no PostgreSQL or Redis required in CI.
"""
import os
import sys

# Set env vars BEFORE importing any backend modules so config picks them up
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_gold_ai.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum-xx")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("ADMIN_PASSWORD", "testpass123")
os.environ.setdefault("ML_MODEL_DIR", "/tmp/goldai_test_models")

# Make both code trees importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "backend"))
sys.path.insert(0, os.path.join(_root, "src"))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def test_engine():
    from database import Base
    # Import all models so they register on the metadata
    import models  # noqa: F401

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    # Enable FK enforcement for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def TestingSessionLocal(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture()
def db(TestingSessionLocal):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(test_engine, TestingSessionLocal):
    from main import app
    from database import get_db

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Register a regular user and return bearer auth headers."""
    client.post("/api/v1/auth/register", json={"email": "user@test.local", "password": "TestPass123!"})
    resp = client.post("/api/v1/auth/login", json={"email": "user@test.local", "password": "TestPass123!"})
    data = resp.json()
    token = data.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, db):
    """Register a user, promote to admin, return auth headers."""
    from models.user import User

    client.post("/api/v1/auth/register", json={"email": "admin@test.local", "password": "AdminPass123!"})
    user = db.query(User).filter(User.email == "admin@test.local").first()
    if user:
        user.is_admin = True
        db.commit()

    resp = client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": "AdminPass123!"})
    data = resp.json()
    token = data.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_candles():
    """300 realistic XAUUSD-like candles for testing."""
    import random
    random.seed(42)
    candles = []
    price = 1900.0
    for _ in range(300):
        change = random.gauss(0, 5)
        open_ = price
        close = price + change
        high = max(open_, close) + random.uniform(0, 3)
        low = min(open_, close) - random.uniform(0, 3)
        volume = random.uniform(100, 1000)
        candles.append({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        price = close
    return candles
