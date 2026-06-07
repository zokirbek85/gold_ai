from fastapi.testclient import TestClient
from src.main import app
from scripts.seed_roles import seed as seed_roles
from src.database.session import SessionLocal
from src.core import security
from src.database import models

client = TestClient(app)


def setup_module(module):
    seed_roles()


def test_market_data_endpoints_require_authentication():
    r = client.get("/api/v1/market-data/candles", params={"symbol": "EURUSD", "timeframe": "1"})
    assert r.status_code == 401


def test_get_ticks_and_candles_after_login():
    email = "market-user@example.com"
    password = "marketpass"
    # ensure user exists
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            role = db.query(models.Role).filter(models.Role.name == "Trader").first()
            if not role:
                role = models.Role(name="Trader", description="Trader role")
                db.add(role)
                db.commit()
                db.refresh(role)
            user = models.User(email=email, hashed_password=security.hash_password(password), role_id=role.id)
            db.add(user)
            db.commit()
            db.refresh(user)
    finally:
        db.close()

    token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/market-data/ticks", params={"symbol": "EURUSD"}, headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r2 = client.get("/api/v1/market-data/candles", params={"symbol": "EURUSD", "timeframe": "1"}, headers=headers)
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)
