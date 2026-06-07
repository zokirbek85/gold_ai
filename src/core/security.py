from datetime import datetime, timedelta
from typing import Any, Optional
import hashlib
import hmac
import os
import jwt
from src.config.settings import settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 120_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        algo, iter_s, salt_hex, dk_hex = hashed.split("$")
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        dk = bytes.fromhex(dk_hex)
        calc = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False


def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded


def create_refresh_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
