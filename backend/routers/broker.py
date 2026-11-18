"""Broker cost feed: MetaTrader EA → backend (token-protected), and the calibration report."""
import hmac
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db

router = APIRouter()


class QuotesIn(BaseModel):
    quotes: List[Dict[str, Any]]


@router.post("/quotes")
def post_quotes(payload: QuotesIn, x_feed_token: Optional[str] = Header(None), db: Session = Depends(get_db)):
    expected = settings.BROKER_FEED_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="Broker feed disabled: set BROKER_FEED_TOKEN in .env")
    if not x_feed_token or not hmac.compare_digest(x_feed_token, expected):
        raise HTTPException(status_code=401, detail="Bad feed token")
    if len(payload.quotes) > 500:
        raise HTTPException(status_code=413, detail="At most 500 quotes per request")
    from services.broker_costs import ingest
    return ingest(db, payload.quotes)


@router.get("/costs")
def get_costs(symbol: str = "XAUUSD", days: int = Query(30, ge=1, le=365), broker: Optional[str] = None,
              db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Real spread/swap vs the RiskConfig assumptions used by backtest, paper and sizing."""
    from services.broker_costs import costs
    return costs(db, symbol=symbol, days=days, broker=broker)
