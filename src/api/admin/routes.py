"""
Admin Panel API — user management, system settings, logs, model management.
All endpoints require Admin role.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import require_role
from src.core.security import hash_password
from src.database import models
from src.database.session import get_db

router = APIRouter()


# ------------------------------------------------------------------ Users
class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime
    role: Optional[str] = None

    class Config:
        from_attributes = True


class CreateUserIn(BaseModel):
    email: str
    password: str
    role: str = "Trader"


class UpdateUserIn(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None


@router.get("/users", response_model=List[UserOut])
def list_users(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    users = db.query(models.User).limit(limit).all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            is_active=u.is_active,
            created_at=u.created_at,
            role=u.role.name if u.role else None,
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut)
def create_user(
    payload: CreateUserIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    role = db.query(models.Role).filter(models.Role.name == payload.role).first()
    if not role:
        role = models.Role(name=payload.role)
        db.add(role)
        db.flush()
    user = models.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(id=user.id, email=user.email, is_active=user.is_active, created_at=user.created_at, role=role.name)


@router.patch("/users/{user_id}", response_model=Dict[str, str])
def update_user(
    user_id: int,
    payload: UpdateUserIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role is not None:
        role = db.query(models.Role).filter(models.Role.name == payload.role).first()
        if not role:
            role = models.Role(name=payload.role)
            db.add(role)
            db.flush()
        user.role_id = role.id
    db.commit()
    return {"status": "updated"}


@router.delete("/users/{user_id}", response_model=Dict[str, str])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


# ------------------------------------------------------------------ Settings
class SettingIn(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


@router.get("/settings", response_model=List[Dict[str, Any]])
def list_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    rows = db.query(models.Setting).all()
    return [{"key": r.key, "value": r.value, "description": r.description} for r in rows]


@router.put("/settings", response_model=Dict[str, str])
def upsert_setting(
    payload: SettingIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    existing = db.query(models.Setting).filter(models.Setting.key == payload.key).first()
    if existing:
        existing.value = payload.value
        if payload.description:
            existing.description = payload.description
    else:
        db.add(models.Setting(key=payload.key, value=payload.value, description=payload.description))
    db.commit()
    return {"status": "ok"}


# ------------------------------------------------------------------ Logs
@router.get("/logs", response_model=List[Dict[str, Any]])
def list_logs(
    level: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    q = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc())
    if level:
        q = q.filter(models.SystemLog.level == level.upper())
    rows = q.limit(limit).all()
    return [{"id": r.id, "level": r.level, "message": r.message, "created_at": r.created_at} for r in rows]


# ------------------------------------------------------------------ Dashboard Stats
@router.get("/stats", response_model=Dict[str, Any])
def admin_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    return {
        "users": db.query(models.User).count(),
        "signals": db.query(models.Signal).count(),
        "candles": db.query(models.Candle).count(),
        "news_articles": db.query(models.NewsArticle).count(),
        "economic_events": db.query(models.EconomicEvent).count(),
        "backtests": db.query(models.Backtest).count(),
        "ai_analyses": db.query(models.AIAnalysis).count(),
    }
