from fastapi import Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
from src.database.session import get_db
from src.core import security
from src.database import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    try:
        data = security.decode_token(token)
        user_id = int(data.get("sub"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user_ws(websocket: WebSocket) -> models.User:
    authorization = websocket.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)
    token = authorization.split(" ", 1)[1]
    try:
        data = security.decode_token(token)
        user_id = int(data.get("sub"))
    except Exception:
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)
    db = next(get_db())
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
    finally:
        db.close()
    if not user:
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)
    return user


def require_role(*role_names: str):
    def _require(current_user: models.User = Depends(get_current_user)):
        if not current_user.role or current_user.role.name not in role_names:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return _require
