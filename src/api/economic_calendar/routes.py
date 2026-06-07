from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.economic_calendar.engine import economic_calendar

router = APIRouter()


class EconEventOut(BaseModel):
    id: int
    provider: str
    event_type: str
    country: str
    scheduled_at: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    surprise: Optional[float] = None
    impact: Optional[int] = None

    class Config:
        from_attributes = True


class ScoreEventIn(BaseModel):
    event_type: str
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None


@router.get("/", response_model=List[EconEventOut])
def list_events(
    limit: int = Query(50, le=200),
    offset: int = 0,
    country: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.EconomicEvent).order_by(models.EconomicEvent.scheduled_at.desc())
    if country:
        q = q.filter(models.EconomicEvent.country == country)
    return q.offset(offset).limit(limit).all()


@router.post("/score", response_model=Dict[str, Any])
def score_event(
    payload: ScoreEventIn,
    current_user: models.User = Depends(get_current_user),
):
    return economic_calendar.score_event(
        event_type=payload.event_type,
        actual=payload.actual,
        forecast=payload.forecast,
        previous=payload.previous,
    )


@router.post("/fetch", response_model=Dict[str, Any])
def fetch_calendar(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    events = economic_calendar.fetch_forexfactory()
    count = 0
    for e in events:
        exists = db.query(models.EconomicEvent).filter(
            models.EconomicEvent.event_type == e["event_type"],
            models.EconomicEvent.scheduled_at == e["scheduled_at"],
        ).first()
        if exists:
            continue
        record = models.EconomicEvent(
            provider=e["provider"],
            event_type=e["event_type"],
            country=e["country"],
            scheduled_at=e["scheduled_at"],
            actual=str(e["actual"]) if e["actual"] is not None else None,
            forecast=str(e["forecast"]) if e["forecast"] is not None else None,
            previous=str(e["previous"]) if e["previous"] is not None else None,
            surprise=None,
            impact=e["impact"],
        )
        db.add(record)
        count += 1
    db.commit()
    return {"fetched": count}


@router.get("/aggregate-score", response_model=Dict[str, Any])
def aggregate_score(
    hours: int = 48,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(models.EconomicEvent).filter(models.EconomicEvent.scheduled_at >= cutoff).all()
    events = []
    for r in rows:
        scored = economic_calendar.score_event(
            r.event_type,
            float(r.actual) if r.actual else None,
            float(r.forecast) if r.forecast else None,
            float(r.previous) if r.previous else None,
        )
        events.append(scored)
    return economic_calendar.aggregate_score(events)
