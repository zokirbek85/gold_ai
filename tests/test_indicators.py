from fastapi.testclient import TestClient
from src.main import app
from scripts.seed_roles import seed as seed_roles
from src.database.session import SessionLocal
from src.core import security
from src.database import models

client = TestClient(app)


def setup_module(module):
    # ensure roles exist
    seed_roles()


import uuid


def test_create_indicator_and_fetch_latest():
    # register a trader (register endpoint assigns Trader role)
    email = f"trader+{uuid.uuid4().hex}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "pass123"})
    assert resp.status_code == 200
    # login
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "pass123"})
    assert resp.status_code == 200
    data = resp.json()
    token = data["access_token"]

    # post indicator
    payload = {"symbol": "XAUUSD", "name": "EMA20", "timeframe": "M1", "value": 2100.5}
    r = client.post(
        "/api/v1/indicators/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    iid = r.json().get("id")
    assert iid is not None

    # fetch latest
    r2 = client.get("/api/v1/indicators/latest", params={"symbol": "XAUUSD", "timeframe": "M1"})
    assert r2.status_code == 200
    arr = r2.json()
    assert any(item["id"] == iid for item in arr)


def test_viewer_cannot_create_indicator():
    # create a viewer user directly in DB
    db = SessionLocal()
    try:
        viewer_role = db.query(models.Role).filter(models.Role.name == "Viewer").first()
        if not viewer_role:
            viewer_role = models.Role(name="Viewer", description="Viewer role")
            db.add(viewer_role)
            db.commit()
            db.refresh(viewer_role)
        hashed = security.hash_password("viewerpass")
        u = db.query(models.User).filter(models.User.email == "viewer@example.com").first()
        if not u:
            u = models.User(email="viewer@example.com", hashed_password=hashed, role_id=viewer_role.id)
            db.add(u)
            db.commit()
            db.refresh(u)
    finally:
        db.close()

    # create token for viewer and attempt to create indicator
    token = security.create_access_token(u.id)
    payload = {"symbol": "XAUUSD", "name": "EMA20", "timeframe": "M1", "value": 2100.5}
    r = client.post(
        "/api/v1/indicators/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
