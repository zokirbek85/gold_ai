from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.calendar_service import get_or_generate_events, get_aggregate_score

router = APIRouter()


class EventOut(BaseModel):
    id: int
    event: str
    currency: str
    impact: int
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    event_time: datetime


@router.get("", response_model=List[EventOut])
def get_events(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    items = get_or_generate_events(db, limit=limit)
    return [
        EventOut(
            id=item["id"],
            event=item["event"],
            currency=item["currency"],
            impact=item["impact"],
            forecast=item.get("forecast"),
            previous=item.get("previous"),
            actual=item.get("actual"),
            event_time=item["event_time"],
        )
        for item in items
    ]


@router.get("/aggregate-score")
def aggregate_score(
    hours: int = Query(48, le=168),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_aggregate_score(db, hours=hours)
