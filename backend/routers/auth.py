import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import get_db
from models.user import User
from config import settings

router = APIRouter()

# ── Redis-backed token blacklist ──────────────────────────────────────────────
try:
    import redis as _redis_mod
    _redis_bl = _redis_mod.Redis.from_url(
        settings.REDIS_URL, decode_responses=True,
        socket_connect_timeout=2, socket_timeout=2,
    )
    _redis_bl.ping()
except Exception:
    _redis_bl = None


def _blacklist_token(jti: str, ttl_seconds: int) -> None:
    if _redis_bl:
        try:
            _redis_bl.setex(f"bl:jwt:{jti}", ttl_seconds, "1")
        except Exception:
            pass


def _is_blacklisted(jti: str) -> bool:
    if _redis_bl:
        try:
            return bool(_redis_bl.exists(f"bl:jwt:{jti}"))
        except Exception:
            pass
    return False


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
    import uuid
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)
    jti = str(uuid.uuid4())
    return jwt.encode(
        {"sub": subject, "type": token_type, "exp": expire, "iat": now, "jti": jti},
        settings.SECRET_KEY, algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    jti = payload.get("jti", "")
    if jti and _is_blacklisted(jti):
        raise JWTError("Token has been revoked")
    return payload


class AuthIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


def _get_current_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        data = decode_token(token)
        return data.get("sub")
    except Exception:
        return None


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
    user.last_login = datetime.now(timezone.utc)
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
        # Rotate: blacklist the old refresh token
        jti = data.get("jti", "")
        if jti:
            _blacklist_token(jti, settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access = create_token(user_id, "access", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_refresh = create_token(user_id, "refresh", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)
    return TokenOut(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    """Blacklist the current access token so it can't be reused."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")
    token = authorization.split(" ", 1)[1]
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"],
                          options={"verify_exp": False})
        jti = data.get("jti", "")
        if jti:
            _blacklist_token(jti, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    except Exception:
        pass
    return {"detail": "Logged out"}
