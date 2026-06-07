"""
Shared pytest fixtures for Gold AI test suite.
Uses SQLite in-memory database — no PostgreSQL or Redis required in CI.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.session import get_db
from src.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Register + login; return bearer auth headers."""
    client.post("/api/v1/auth/register", json={"email": "test@gold.ai", "password": "TestPass123!"})
    resp = client.post("/api/v1/auth/login", json={"email": "test@gold.ai", "password": "TestPass123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client):
    """Register + promote to Admin + login."""
    client.post("/api/v1/auth/register", json={"email": "admin@gold.ai", "password": "AdminPass123!"})
    # Promote via direct DB
    db = TestingSessionLocal()
    from src.database import models
    from src.core.security import hash_password
    role = db.query(models.Role).filter(models.Role.name == "Admin").first()
    if not role:
        role = models.Role(name="Admin", description="Administrator")
        db.add(role)
        db.commit()
        db.refresh(role)
    user = db.query(models.User).filter(models.User.email == "admin@gold.ai").first()
    if user:
        user.role_id = role.id
        db.commit()
    db.close()
    resp = client.post("/api/v1/auth/login", json={"email": "admin@gold.ai", "password": "AdminPass123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_candles():
    """Generate 300 realistic XAUUSD-like candles for testing."""
    import random
    random.seed(42)
    candles = []
    price = 1900.0
    for i in range(300):
        change = random.gauss(0, 5)
        open_ = price
        close = price + change
        high = max(open_, close) + random.uniform(0, 3)
        low = min(open_, close) - random.uniform(0, 3)
        volume = random.uniform(100, 1000)
        candles.append({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        price = close
    return candles
