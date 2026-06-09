"""Risk management API — daily loss limits, open trade counts, weekly drawdown."""
from __future__ import annotations

from fastapi import APIRouter, Query
from core.risk_tracker import get_risk_tracker

router = APIRouter()


@router.get("/status")
def risk_status(
    account_id: str = Query("default"),
    account_balance: float = Query(10000.0, ge=100),
):
    """Return current risk metrics for an account."""
    return get_risk_tracker().status(account_id, account_balance)


@router.get("/can-trade")
def can_trade(
    account_id: str = Query("default"),
    account_balance: float = Query(10000.0, ge=100),
    symbol: str = Query("XAUUSD"),
):
    """Check whether opening a new trade is permitted given current risk state."""
    return get_risk_tracker().can_trade(account_id, account_balance, symbol)
