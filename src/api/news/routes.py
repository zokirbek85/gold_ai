from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.news_engine.analyzer import news_analyzer
from src.news_engine.service import news_service

router = APIRouter()


class NewsOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    published_at: datetime
    summary: Optional[str] = None
    impact_score: Optional[int] = None
    confidence: Optional[float] = None
    duration: Optional[str] = None
    reliability: Optional[float] = None

    class Config:
        from_attributes = True


class AnalyzeIn(BaseModel):
    title: str
    content: str = ""


@router.get("/", response_model=List[NewsOut])
def list_news(
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.NewsArticle)
        .order_by(models.NewsArticle.published_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows


@router.get("/sentiment", response_model=Dict[str, Any])
def news_sentiment(
    hours: int = 24,
    current_user: models.User = Depends(get_current_user),
):
    return news_service.get_sentiment(hours=hours)


@router.post("/ingest", response_model=Dict[str, Any])
def trigger_ingest(
    current_user: models.User = Depends(require_role("Admin")),
):
    count = news_service.run_ingest()
    return {"ingested": count}


@router.post("/analyze", response_model=Dict[str, Any])
def analyze_text(
    payload: AnalyzeIn,
    current_user: models.User = Depends(get_current_user),
):
    result = news_analyzer.analyze_article({"title": payload.title, "content": payload.content})
    return {k: v for k, v in result.items() if k not in ("title", "content")}
