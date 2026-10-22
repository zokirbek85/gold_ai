import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle
from models.signal import Signal
from services.signal_service import generate_signal, enrich_signal, _compute_sl_tp, _calc_atr
from services.market_service import fetch_and_store
from services.news_service import get_sentiment_summary, refresh_news
from services.calendar_service import get_aggregate_score, refresh_calendar
from services.telegram_service import alert_signal
from src.signals.scorer import signal_scorer

router = APIRouter()


class SignalOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    signal_type: str
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tp1: Optional[float] = None
    tp3: Optional[float] = None
    rr: Optional[float] = None
    confidence: Optional[float] = None
    technical_score: Optional[float] = None
    smc_score: Optional[float] = None
    ml_score: Optional[float] = None
    news_score: Optional[float] = None
    economic_score: Optional[float] = None
    reasoning: Optional[str] = None
    created_at: datetime
    lot_size: Optional[float] = None
    risk_amount_usd: Optional[float] = None
    plain_explanation: Optional[str] = None
    signal_emoji: Optional[str] = None
    sl_distance_pct: Optional[float] = None
    tp1_distance_pct: Optional[float] = None
    tp2_distance_pct: Optional[float] = None
    tp3_distance_pct: Optional[float] = None

    class Config:
        from_attributes = True


class GenerateSignalIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    account_balance: float = 10000.0
    # Multi-timeframe confluence timeframes
    timeframe_trend:   str = "240"   # H4 — trend direction
    timeframe_primary: str = "60"    # H1 — signal direction (mirrors timeframe by default)
    timeframe_confirm: str = "15"    # M15 — entry trigger


def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 300) -> list:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [{"open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
            for r in rows]


def _apply_confluence(
    result: Dict[str, Any],
    candles_h4: list,
    candles_h1: list,
    candles_m15: list,
) -> Dict[str, Any]:
    """
    Compute multi-TF confluence and blend it into the signal result dict.
    Mutates and returns result.
    """
    from config import settings as _s

    direction = result.get("direction", "neutral")
    # Use combined_score (not composite_score) to determine directional bias
    combined = float(result.get("combined_score", 50.0))
    conf_dir = direction if direction != "neutral" else (
        "bullish" if combined > 50 else "bearish"
    )

    confluence = signal_scorer.confluence_score(candles_h4, candles_h1, candles_m15, conf_dir)
    alignment  = confluence["alignment"]

    composite = combined
    if alignment == "full":
        composite = min(100.0, composite + 8)
    elif alignment == "partial":
        composite = min(100.0, composite + 3)
    else:  # conflict
        composite = max(0.0, composite - 10)
        if composite < 70 and result.get("signal_type") != "NO TRADE":
            result["signal_type"] = "NO TRADE"
            result["direction"]   = "neutral"
            result["stop_loss"]   = None
            result["take_profit"] = None
            result["tp1"]         = None
            result["risk_reward"] = None

    # Upgrade NEUTRAL → BUY/SELL when confluence bonus crosses threshold
    if result.get("signal_type") == "NEUTRAL" and result.get("entry"):
        atr = _calc_atr(candles_h1)
        entry = float(result["entry"])
        if composite >= _s.SIGNAL_BUY_THRESHOLD:
            sl, tp1, tp2, tp3 = _compute_sl_tp("BUY", entry, candles_h1, atr)
            rr = round(abs(tp2 - entry) / (abs(entry - sl) + 1e-9), 2) if sl and tp2 else None
            conf = round(min(abs(composite - 50) * 3.33, 100), 1)
            result.update({"signal_type": "BUY", "stop_loss": sl,
                           "take_profit": tp2, "tp1": tp1, "tp3": tp3,
                           "rr": rr, "confidence": conf})
        elif composite <= _s.SIGNAL_SELL_THRESHOLD:
            sl, tp1, tp2, tp3 = _compute_sl_tp("SELL", entry, candles_h1, atr)
            rr = round(abs(tp2 - entry) / (abs(entry - sl) + 1e-9), 2) if sl and tp2 else None
            conf = round(min(abs(composite - 50) * 3.33, 100), 1)
            result.update({"signal_type": "SELL", "stop_loss": sl,
                           "take_profit": tp2, "tp1": tp1, "tp3": tp3,
                           "rr": rr, "confidence": conf})

    result["composite_score"] = round(composite, 1)
    result["confluence"]      = confluence
    return result


@router.post("/generate")
def generate(
    payload: GenerateSignalIn,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from config import settings as _s
    if _s.SIGNAL_ENGINE.lower() == "legacy":
        return _generate_legacy(payload, db)
    return _generate_v2(payload, db)


def _live_price(symbol: str, max_age_s: float = 120.0):
    """Twelvedata WS price if fresh. Its bid/ask are synthetic, so they are not used."""
    from services.twelvedata_service import get_price
    tick = get_price(symbol)
    if not tick or not tick.get("price"):
        return None, None
    try:
        ts = datetime.fromisoformat(str(tick.get("time")).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - ts).total_seconds() > max_age_s:
            return None, "twelvedata_ws_stale"
    except ValueError:
        return None, "twelvedata_ws_bad_time"
    return float(tick["price"]), "twelvedata_ws"


def _generate_v2(payload: GenerateSignalIn, db: Session) -> Dict[str, Any]:
    from models.economic_calendar import EconomicEvent
    from strategy.config import StrategyConfig
    from strategy.live import generate as live_generate, legacy_view

    cfg = StrategyConfig()
    tf_p, tf_c = str(cfg.primary_tf), str(cfg.context_tf)
    for tf, limit in ((tf_p, 500), (tf_c, 300)):
        try:
            fetch_and_store(db, payload.symbol, tf, limit=limit)
        except Exception:
            db.rollback()  # provider down → decide on stored data; staleness check will catch it
    try:
        refresh_calendar(db)
    except Exception:
        db.rollback()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    events = [
        {"event": e.event, "currency": e.currency, "impact": e.impact, "event_time": e.event_time}
        for e in db.query(EconomicEvent).filter(
            EconomicEvent.event_time >= now - timedelta(hours=2),
            EconomicEvent.event_time <= now + timedelta(hours=2),
        ).all()
    ]
    price, price_src = _live_price(payload.symbol)

    sig = live_generate(
        _load_candles(db, payload.symbol, tf_p, limit=1500),
        _load_candles(db, payload.symbol, tf_c, limit=400),
        symbol=payload.symbol, now=now, events=events,
        live_price=price, live_price_source=price_src,
        account_balance=payload.account_balance, cfg=cfg,
    )
    view = legacy_view(sig)
    if payload.timeframe != tf_p:
        sig["note"] = f"So'ralgan timeframe {payload.timeframe} e'tiborsiz qoldirildi: v2 faqat tasdiqlangan {tf_p} da ishlaydi"

    # De-duplicate: one stored row (and one alert) per closed bar and decision
    last = (db.query(Signal).filter(Signal.symbol == payload.symbol, Signal.timeframe == tf_p)
            .order_by(Signal.created_at.desc()).first())
    bar_close = datetime.fromisoformat(view["bar_close"]) if view.get("bar_close") else None
    duplicate = bool(
        last and bar_close and last.signal_type == view["signal_type"]
        and _naive(last.created_at) >= bar_close
        and (view["signal_type"] == "NO TRADE" or (last.entry == view["entry"] and last.stop_loss == view["stop_loss"]))
    )
    if duplicate:
        sig_id, created = last.id, last.created_at
    else:
        cols = {c.name for c in Signal.__table__.columns}
        row = Signal(**{k: v for k, v in view.items() if k in cols and k not in ("id", "created_at")})
        db.add(row)
        db.commit()
        db.refresh(row)
        sig_id, created = row.id, row.created_at

    result = {**sig, **view, "id": sig_id, "created_at": created, "duplicate": duplicate}
    if view["signal_type"] in ("BUY", "SELL") and not duplicate:
        threading.Thread(target=alert_signal, args=(result,), daemon=True).start()
    return result


def _naive(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def _generate_legacy(payload: GenerateSignalIn, db: Session) -> Dict[str, Any]:
    # Fetch fresh candles from Twelvedata and upsert; use result directly (not re-query)
    fresh_rows = fetch_and_store(db, payload.symbol, payload.timeframe, limit=300)
    candles = [
        {"open": r.open, "high": r.high, "low": r.low,
         "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
        for r in fresh_rows
    ]

    if len(candles) < 50:
        raise HTTPException(
            status_code=422,
            detail="Insufficient candle data. Try again after data ingestion completes.",
        )

    # Refresh news and economic calendar before scoring so sentiment is current
    try:
        refresh_news(db)
    except Exception:
        pass
    try:
        refresh_calendar(db)
    except Exception:
        pass

    news_data  = get_sentiment_summary(db, hours=24)
    econ_data  = get_aggregate_score(db, hours=48)
    news_score = float(news_data.get("score", 50.0))
    econ_score = float(econ_data.get("score", 50.0))

    news_dir  = news_data.get("direction", "neutral")
    news_bull = news_data.get("bullish_count", 0)
    news_bear = news_data.get("bearish_count", 0)
    news_parts = [f"News {news_dir} ({news_bull}↑/{news_bear}↓)"]
    econ_parts = [f"Econ events: {econ_data.get('event_count', 0)} ({econ_score:.0f})"]

    result = generate_signal(
        candles,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        news_score=news_score,
        economic_score=econ_score,
        news_parts=news_parts,
        econ_parts=econ_parts,
    )

    # ── Multi-timeframe confluence ──────────────────────────────────────────
    # Fetch and refresh confluence timeframes too, then re-query with correct order
    fetch_and_store(db, payload.symbol, payload.timeframe_trend,   limit=300)
    fetch_and_store(db, payload.symbol, payload.timeframe_confirm, limit=300)

    candles_trend   = _load_candles(db, payload.symbol, payload.timeframe_trend)
    candles_primary = _load_candles(db, payload.symbol, payload.timeframe_primary)
    candles_confirm = _load_candles(db, payload.symbol, payload.timeframe_confirm)

    if len(candles_trend) >= 50 and len(candles_primary) >= 50 and len(candles_confirm) >= 50:
        result = _apply_confluence(result, candles_trend, candles_primary, candles_confirm)
    else:
        result.setdefault("confluence", None)

    # Enrich with lot size, distances, plain explanation
    result = enrich_signal(result, payload.account_balance)

    sig = Signal(
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        signal_type=result["signal_type"],
        entry=result.get("entry"),
        stop_loss=result.get("stop_loss"),
        take_profit=result.get("take_profit"),
        tp1=result.get("tp1"),
        tp3=result.get("tp3"),
        rr=result.get("rr"),
        confidence=result.get("confidence"),
        technical_score=result.get("technical_score"),
        smc_score=result.get("smc_score"),
        ml_score=result.get("ml_score"),
        news_score=result.get("news_score"),
        economic_score=result.get("economic_score"),
        reasoning=result.get("reasoning"),
        lot_size=result.get("lot_size"),
        risk_amount_usd=result.get("risk_amount_usd"),
        plain_explanation=result.get("plain_explanation"),
        signal_emoji=result.get("signal_emoji"),
        sl_distance_pct=result.get("sl_distance_pct"),
        tp1_distance_pct=result.get("tp1_distance_pct"),
        tp2_distance_pct=result.get("tp2_distance_pct"),
        tp3_distance_pct=result.get("tp3_distance_pct"),
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)

    result["id"]         = sig.id
    result["created_at"] = sig.created_at

    # Send Telegram alert for BUY/SELL signals (non-blocking)
    threading.Thread(target=alert_signal, args=(result,), daemon=True).start()

    return result


@router.get("", response_model=List[SignalOut])
def list_signals(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
) -> List[Signal]:
    q = db.query(Signal).order_by(Signal.created_at.desc())
    if symbol:
        q = q.filter(Signal.symbol == symbol)
    if timeframe:
        q = q.filter(Signal.timeframe == timeframe)
    return q.limit(limit).all()


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: int, db: Session = Depends(get_db)) -> Signal:
    sig = db.query(Signal).filter(Signal.id == signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig
