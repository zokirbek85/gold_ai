"""
Seed initial roles and permissions.
Run with: PYTHONPATH=/app python /app/scripts/seed_roles.py
"""
from src.database.session import engine, SessionLocal
from src.database import models


def seed():
    db = SessionLocal()
    try:
        # ensure tables exist
        models.Base.metadata.create_all(bind=engine)

        # create roles
        roles = ["Admin", "Trader", "Viewer"]
        for r in roles:
            exists = db.query(models.Role).filter(models.Role.name == r).first()
            if not exists:
                db.add(models.Role(name=r, description=f"{r} role"))

        # create some example permissions
        perms = ["manage_users", "create_signals", "view_reports"]
        for p in perms:
            exists = db.query(models.Permission).filter(models.Permission.name == p).first()
            if not exists:
                db.add(models.Permission(name=p, description=f"{p}"))

        db.commit()
        print("Seeded roles and permissions")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
