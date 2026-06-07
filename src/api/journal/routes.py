"""Trade Journal API — log, track, and review trade outcomes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import models
from src.database.session import get_db

router = APIRouter()

# ── Pydantic schemas ────────────────────────────────────────────────────────


class JournalEntryIn(BaseModel):
    symbol: str = "XAUUSD"
    direction: Literal["BUY", "SELL"]
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float = Field(gt=0)
    signal_id: Optional[int] = None
    emotion_rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None
    opened_at: Optional[datetime] = None  # defaults to utcnow if omitted


class CloseEntryIn(BaseModel):
    exit_price: float
    exit_reason: Literal["tp_hit", "sl_hit", "manual", "time_exit"] = "manual"
    notes: Optional[str] = None
    emotion_rating: Optional[int] = Field(None, ge=1, le=5)


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[int] = None
    signal_id: Optional[int] = None
    symbol: str
    direction: str
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    lot_size: float
    status: str
    pnl_usd: Optional[float] = None
    pnl_pips: Optional[float] = None
    exit_reason: Optional[str] = None
    emotion_rating: Optional[int] = None
    notes: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    created_at: datetime
    risk_reward_actual: Optional[float] = None


class StatsOut(BaseModel):
    total_trades: int
    win_rate_pct: float
    total_pnl_usd: float
    avg_rr: Optional[float]
    best_trade_pnl: Optional[float]
    worst_trade_pnl: Optional[float]
    streak_current: int   # positive = win streak, negative = loss streak


# ── Helpers ─────────────────────────────────────────────────────────────────


def _get_entry_or_404(entry_id: str, db: Session) -> models.TradeJournal:
    entry = db.query(models.TradeJournal).filter(models.TradeJournal.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry


def _calc_pnl(direction: str, entry_price: float, exit_price: float, lot_size: float):
    """Returns (pnl_usd, pnl_pips). Works for XAUUSD (1 lot = 100 oz, pip = $0.01)."""
    mult = 1 if direction == "BUY" else -1
    pnl_usd  = (exit_price - entry_price) * mult * lot_size * 100
    pnl_pips = (exit_price - entry_price) * mult / 0.01
    return round(pnl_usd, 2), round(pnl_pips, 1)


def _streak(closed_trades: list) -> int:
    """Consecutive win (+n) or loss (−n) streak from most-recent trade first."""
    if not closed_trades:
        return 0
    first_is_win = (closed_trades[0].pnl_usd or 0) > 0
    streak = 0
    for t in closed_trades:
        is_win = (t.pnl_usd or 0) > 0
        if is_win == first_is_win:
            streak += 1
        else:
            break
    return streak if first_is_win else -streak


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/", response_model=JournalEntryOut, status_code=201)
def create_entry(
    payload: JournalEntryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.TradeJournal:
    """Open a new trade journal entry."""
    if payload.signal_id is not None:
        sig = db.query(models.Signal).filter(models.Signal.id == payload.signal_id).first()
        if not sig:
            raise HTTPException(status_code=422, detail=f"Signal {payload.signal_id} not found")

    entry = models.TradeJournal(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        signal_id=payload.signal_id,
        symbol=payload.symbol,
        direction=payload.direction,
        entry_price=payload.entry_price,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
        lot_size=payload.lot_size,
        status="open",
        emotion_rating=payload.emotion_rating,
        notes=payload.notes,
        opened_at=payload.opened_at or datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/stats", response_model=StatsOut)
def get_stats(
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> StatsOut:
    """Aggregate performance statistics for the current user's journal."""
    q = db.query(models.TradeJournal).filter(
        models.TradeJournal.user_id == current_user.id,
        models.TradeJournal.status != "cancelled",
    )
    if symbol:
        q = q.filter(models.TradeJournal.symbol == symbol)

    all_trades = q.all()
    closed = [t for t in all_trades if t.status == "closed" and t.pnl_usd is not None]

    total_trades = len(all_trades)
    wins = [t for t in closed if t.pnl_usd > 0]
    win_rate_pct = round(len(wins) / len(closed) * 100, 1) if closed else 0.0
    total_pnl_usd = round(sum(t.pnl_usd for t in closed), 2) if closed else 0.0

    rr_values = [t.risk_reward_actual for t in closed if t.risk_reward_actual is not None]
    avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else None

    pnl_values = [t.pnl_usd for t in closed]
    best_trade_pnl  = round(max(pnl_values), 2) if pnl_values else None
    worst_trade_pnl = round(min(pnl_values), 2) if pnl_values else None

    closed_by_date = sorted(closed, key=lambda t: t.closed_at or datetime.min, reverse=True)
    streak_current = _streak(closed_by_date)

    return StatsOut(
        total_trades=total_trades,
        win_rate_pct=win_rate_pct,
        total_pnl_usd=total_pnl_usd,
        avg_rr=avg_rr,
        best_trade_pnl=best_trade_pnl,
        worst_trade_pnl=worst_trade_pnl,
        streak_current=streak_current,
    )


@router.get("/", response_model=List[JournalEntryOut])
def list_entries(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list:
    """List journal entries with optional filtering."""
    q = db.query(models.TradeJournal).filter(
        models.TradeJournal.user_id == current_user.id,
    ).order_by(models.TradeJournal.opened_at.desc())

    if status:
        q = q.filter(models.TradeJournal.status == status)
    if symbol:
        q = q.filter(models.TradeJournal.symbol == symbol)

    return q.offset(offset).limit(limit).all()


@router.get("/{entry_id}", response_model=JournalEntryOut)
def get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.TradeJournal:
    """Get a single journal entry by ID."""
    entry = _get_entry_or_404(entry_id, db)
    if entry.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your journal entry")
    return entry


@router.patch("/{entry_id}/close", response_model=JournalEntryOut)
def close_entry(
    entry_id: str,
    payload: CloseEntryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.TradeJournal:
    """
    Close an open journal entry.
    Auto-calculates pnl_usd and pnl_pips from exit_price.
    """
    entry = _get_entry_or_404(entry_id, db)
    if entry.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your journal entry")
    if entry.status != "open":
        raise HTTPException(status_code=422, detail=f"Entry is already '{entry.status}'")

    pnl_usd, pnl_pips = _calc_pnl(
        entry.direction, entry.entry_price, payload.exit_price, entry.lot_size
    )

    entry.exit_price     = payload.exit_price
    entry.exit_reason    = payload.exit_reason
    entry.pnl_usd        = pnl_usd
    entry.pnl_pips       = pnl_pips
    entry.status         = "closed"
    entry.closed_at      = datetime.utcnow()
    if payload.notes is not None:
        entry.notes = payload.notes
    if payload.emotion_rating is not None:
        entry.emotion_rating = payload.emotion_rating

    db.commit()
    db.refresh(entry)
    return entry
