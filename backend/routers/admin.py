from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.candle import Candle
from models.signal import Signal
from models.news import NewsArticle
from models.system_log import SystemLog

router = APIRouter()


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class LogOut(BaseModel):
    timestamp: datetime
    level: str
    message: str

    class Config:
        from_attributes = True


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return {
        "signals": db.query(Signal).count(),
        "candles": db.query(Candle).count(),
        "news_articles": db.query(NewsArticle).count(),
        "users": db.query(User).count(),
        "last_updated": datetime.utcnow().isoformat(),
    }


@router.get("/users", response_model=List[UserOut])
def list_users(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
) -> List[User]:
    return db.query(User).order_by(User.created_at.desc()).limit(limit).all()


@router.get("/logs", response_model=List[LogOut])
def list_logs(
    level: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
) -> List[SystemLog]:
    q = db.query(SystemLog).order_by(SystemLog.timestamp.desc())
    if level:
        q = q.filter(SystemLog.level == level.upper())
    return q.limit(limit).all()
