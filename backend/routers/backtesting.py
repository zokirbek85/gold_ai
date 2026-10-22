from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle
from models.backtest import BacktestResult
from services.signal_service import generate_signal

router = APIRouter()


class BacktestIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    window: int = 100


class BacktestOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    avg_rr: Optional[float] = None
    max_drawdown: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


def _run_backtest(candles: list, window: int) -> Dict[str, Any]:
    """LEGACY backtest (SIGNAL_ENGINE=legacy only).

    Known flaws, kept for comparison: no spread/slippage, 5-bar horizon with
    unresolved trades silently dropped, overlapping trades, and
    ``max_drawdown`` is the longest loss streak, not a drawdown.
    """
    if len(candles) < window + 5:
        return {"error": f"Need at least {window + 5} candles"}

    trades: List[Dict[str, float]] = []
    start = max(50, len(candles) - window)

    for i in range(start, len(candles) - 5):
        window_candles = candles[:i + 1]
        sig = generate_signal(window_candles)

        if sig["signal_type"] not in ("BUY", "SELL"):
            continue

        entry = sig.get("entry")
        sl    = sig.get("stop_loss")
        tp2   = sig.get("take_profit")

        if not entry or not sl or not tp2:
            continue

        future = candles[i + 1 : i + 6]
        future_highs = [float(c["high"]) for c in future]
        future_lows = [float(c["low"]) for c in future]

        if sig["signal_type"] == "BUY":
            hit_tp = any(h >= tp2 for h in future_highs)
            hit_sl = any(l <= sl for l in future_lows)
            if hit_tp and not hit_sl:
                rr = abs(tp2 - entry) / (abs(entry - sl) + 1e-9)
                trades.append({"win": True, "rr": rr})
            elif hit_sl:
                trades.append({"win": False, "rr": 1.0})
        else:
            hit_tp = any(l <= tp2 for l in future_lows)
            hit_sl = any(h >= sl for h in future_highs)
            if hit_tp and not hit_sl:
                rr = abs(tp2 - entry) / (abs(entry - sl) + 1e-9)
                trades.append({"win": True, "rr": rr})
            elif hit_sl:
                trades.append({"win": False, "rr": 1.0})

    if not trades:
        return {"error": "No completed trades in backtest window"}

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    win_rate = len(wins) / len(trades)
    total_win_r = sum(t["rr"] for t in wins)
    total_loss_r = len(losses)
    profit_factor = total_win_r / (total_loss_r + 1e-9)
    avg_rr = sum(t["rr"] for t in wins) / (len(wins) + 1e-9)

    # Max drawdown (consecutive losses)
    max_dd = 0
    current_dd = 0
    for t in trades:
        if not t["win"]:
            current_dd += 1
            max_dd = max(max_dd, current_dd)
        else:
            current_dd = 0

    return {
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2),
        "total_trades": len(trades),
        "avg_rr": round(avg_rr, 2),
        "max_drawdown": max_dd,
    }


def _load(db: Session, symbol: str, timeframe: str, limit: int) -> list:
    rows = (db.query(Candle).filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc()).limit(limit).all())
    return [{"timestamp": r.timestamp, "open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume} for r in reversed(rows)]


def run_v2_backtest(primary: list, context: list, window: int, balance: float = 10000.0) -> Dict[str, Any]:
    """Cost-aware v2 backtest over the last ``window`` clean primary bars."""
    from strategy.backtest import metrics as bt_metrics, simulate, v2_decider
    from strategy.config import RiskConfig, StrategyConfig
    from strategy.data_quality import clean_candles
    from strategy.engine import attach_context, prepare_context, prepare_primary

    cfg, rc = StrategyConfig(), RiskConfig()
    p_df, p_rep = clean_candles(primary, cfg.primary_tf)
    c_df, c_rep = clean_candles(context, cfg.context_tf)
    if len(p_df) < cfg.min_history_bars + 20:
        return {"error": f"Need ≥ {cfg.min_history_bars + 20} clean {cfg.primary_tf}m candles, have {len(p_df)}"}
    p = attach_context(prepare_primary(p_df, cfg), prepare_context(c_df, cfg))
    start = max(cfg.min_history_bars, len(p) - window)
    res = simulate(p, v2_decider(p, cfg, rc), rc, cfg.max_hold_bars, start, len(p))
    m = bt_metrics(res["trades"], rc.risk_pct)
    trades = m.get("trades", 0)
    wins = sum(1 for t in res["trades"] if t.r > 0)
    total_pnl = None
    if trades:
        eq = balance
        for t in res["trades"]:
            eq *= 1 + t.r * rc.risk_pct / 100.0
        total_pnl = round(eq - balance, 2)
    return {
        "name": f"v2 {cfg.primary_tf}m/{cfg.context_tf}m · costs incl.",
        "engine": "v2",
        "trade_count": trades,
        "candle_count": len(p) - start,
        "period": [str(p["timestamp"].iloc[start]), str(p["timestamp"].iloc[-1])],
        "metrics": {
            "total_trades": trades, "winning_trades": wins, "losing_trades": trades - wins,
            "win_rate": m.get("win_rate"), "profit_factor": m.get("profit_factor"),
            "max_drawdown_pct": m.get("max_drawdown_pct"), "avg_rr": m.get("avg_win_r"),
            "expectancy_r": m.get("expectancy_r"), "total_pnl": total_pnl,
            "sharpe_ratio": None, "sortino_ratio": None,  # not computed — not fabricated
            **{k: v for k, v in m.items() if k not in ("trades", "win_rate", "profit_factor", "max_drawdown_pct")},
        },
        "costs": {"spread": rc.spread, "slippage": rc.slippage, "commission_per_lot": rc.commission_per_lot},
        "data_quality": {"primary": p_rep.to_dict(), "context": c_rep.to_dict()},
        "skipped": res["skipped"],
        "warning": "Kam savdo soni — natija statistik jihatdan ishonchsiz bo'lishi mumkin" if trades < 100 else None,
        # flat keys kept for older clients / BacktestResult table
        "win_rate": round((m.get("win_rate") or 0) / 100, 4),
        "profit_factor": m.get("profit_factor") or 0.0,
        "total_trades": trades,
        "avg_rr": m.get("avg_win_r") or 0.0,
        "max_drawdown": m.get("max_drawdown_r") or 0.0,
    }


@router.post("/run")
def run_backtest(payload: BacktestIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    from config import settings
    if settings.SIGNAL_ENGINE.lower() != "legacy":
        from strategy.config import StrategyConfig
        cfg = StrategyConfig()
        window = max(100, payload.window)
        result = run_v2_backtest(
            _load(db, payload.symbol, str(cfg.primary_tf), window + 1500),
            _load(db, payload.symbol, str(cfg.context_tf), 1000),
            window,
        )
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        record = BacktestResult(
            symbol=payload.symbol, timeframe=str(cfg.primary_tf),
            win_rate=result["win_rate"], profit_factor=result["profit_factor"],
            total_trades=result["total_trades"], avg_rr=result["avg_rr"],
            max_drawdown=result["max_drawdown"],  # in R units for the v2 engine
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        result["id"] = record.id
        return result

    rows = (
        db.query(Candle)
        .filter(Candle.symbol == payload.symbol, Candle.timeframe == str(payload.timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(payload.window + 100)
        .all()
    )
    rows = list(reversed(rows))

    if len(rows) < payload.window + 5:
        raise HTTPException(status_code=422, detail=f"Need at least {payload.window + 5} candles. Only {len(rows)} available.")

    candles = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
    result = _run_backtest(candles, payload.window)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    record = BacktestResult(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        win_rate=result["win_rate"],
        profit_factor=result["profit_factor"],
        total_trades=result["total_trades"],
        avg_rr=result["avg_rr"],
        max_drawdown=result["max_drawdown"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    result["id"] = record.id
    return result


@router.get("", response_model=List[BacktestOut])
def list_backtests(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
) -> List[BacktestResult]:
    return db.query(BacktestResult).order_by(BacktestResult.created_at.desc()).limit(limit).all()
