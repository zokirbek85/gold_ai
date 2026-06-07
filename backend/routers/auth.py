import hashlib
import hmac
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import get_db
from models.user import User
from config import settings

router = APIRouter()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return f"pbkdf2$sha256${salt.hex()}${dk.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _, algo, salt_hex, dk_hex = hashed.split("$")
        salt = bytes.fromhex(salt_hex)
        dk = bytes.fromhex(dk_hex)
        calc = hashlib.pbkdf2_hmac(algo, plain.encode(), salt, 260_000)
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False


def create_token(subject: str, token_type: str, expires_minutes: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode({"sub": subject, "type": token_type, "exp": expire}, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


class AuthIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/register", response_model=TokenOut)
def register(payload: AuthIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    access = create_token(str(user.id), "access", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh = create_token(str(user.id), "refresh", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenOut)
def login(payload: AuthIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user.last_login = datetime.utcnow()
    db.commit()
    access = create_token(str(user.id), "access", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh = create_token(str(user.id), "refresh", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh_token(payload: RefreshIn):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = data["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access = create_token(user_id, "access", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh = create_token(user_id, "refresh", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)
    return TokenOut(access_token=access, refresh_token=refresh)
