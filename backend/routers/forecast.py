from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.forecast_service import generate_forecast
from services.historical_analysis import monthly_seasonality

router = APIRouter()


@router.get("")
def forecast(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return generate_forecast(db, symbol, timeframe)


@router.get("/historical")
def historical_seasonality(
    symbol: str = Query("XAUUSD"),
    month: int = Query(..., ge=1, le=12, description="Calendar month 1–12"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return historical seasonality stats for a given symbol and calendar month."""
    result = monthly_seasonality(db, symbol, month)
    if result.get("insufficient_data"):
        return {"symbol": symbol, "month": month, "insufficient_data": True}
    return {"symbol": symbol, **result}
