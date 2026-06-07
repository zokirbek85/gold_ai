from scripts.seed_roles import seed as seed_roles
from src.database.session import SessionLocal
from src.database import models


def test_seed_roles_creates_roles():
    seed_roles()
    db = SessionLocal()
    try:
        roles = db.query(models.Role).all()
        names = [r.name for r in roles]
        assert "Admin" in names
        assert "Trader" in names
        assert "Viewer" in names
    finally:
        db.close()
