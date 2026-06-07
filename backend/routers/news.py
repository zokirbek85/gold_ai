from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.news_service import get_or_generate_news, get_sentiment_summary

router = APIRouter()


class NewsOut(BaseModel):
    id: int
    title: str
    source: str
    url: Optional[str] = None
    sentiment: str
    impact_score: float
    published_at: datetime
    duration: Optional[str] = None


@router.get("", response_model=List[NewsOut])
def get_news(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    items = get_or_generate_news(db, limit=limit)
    return [
        NewsOut(
            id=item["id"],
            title=item["title"],
            source=item["source"],
            url=item.get("url"),
            sentiment=item["sentiment"],
            impact_score=item["impact_score"],
            published_at=item["published_at"],
            duration=item.get("duration"),
        )
        for item in items
    ]


@router.get("/sentiment")
def news_sentiment(
    hours: int = Query(24, le=168),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_sentiment_summary(db, hours=hours)
