from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.database import models
from src.core import security

router = APIRouter()


class AuthIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=dict)
def register(payload: AuthIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = security.hash_password(payload.password)
    role = db.query(models.Role).filter(models.Role.name == "Trader").first()
    if not role:
        role = models.Role(name="Trader", description="Default trader role")
        db.add(role)
        db.commit()
        db.refresh(role)
    new = models.User(email=payload.email, hashed_password=hashed, role_id=role.id)
    db.add(new)
    db.commit()
    db.refresh(new)
    return {"id": new.id, "email": new.email}


@router.post("/login", response_model=TokenOut)
def login(payload: AuthIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not security.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = security.create_access_token(user.id)
    refresh = security.create_refresh_token(user.id)
    return {"access_token": access, "refresh_token": refresh}


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn):
    try:
        data = security.decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = data.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access = security.create_access_token(user_id)
    refresh = security.create_refresh_token(user_id)
    return {"access_token": access, "refresh_token": refresh}
