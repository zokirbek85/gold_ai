from typing import Any, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.forecast_service import generate_forecast

router = APIRouter()


@router.get("")
def forecast(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return generate_forecast(db, symbol, timeframe)
