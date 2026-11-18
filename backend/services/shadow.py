"""
Shadow tracking of candidate strategies (forward test, no trading).

``squeeze_trend`` failed the pre-registered acceptance in docs/research/VOL_LAB_2026-11.md
only because its 2020–23 train period lost money. The honest way to learn more is
FORWARD data the parameters have never seen: every hour the candidate is evaluated
on the last closed H1 bar exactly as in the backtest, the decision is stored in
``shadow_signals`` and its result is measured — no paper position, no trade alert.

Parity with ``strategy.backtest.simulate``:
  * decision on the closed bar, same decider (``strategy.vol_lab``), same configs;
  * D1 context resampled from H4, as in the lab;
  * fill at the next bar's open (cancelled if that open is beyond SL/TP);
  * SL first when SL and TP are inside one bar, gap through SL, 48-bar time exit;
  * one position at a time: a signal while the previous one is unresolved is skipped.

Forward acceptance (fixed now): ≥ 30 resolved trades AND CI95 lower bound > 0 AND
expectancy above the random D1-trend control p90 measured in the lab (+0.315 R).
Only then may the candidate go through the registry into paper trading.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.shadow import ShadowSignal

log = logging.getLogger(__name__)

SYMBOL = "XAUUSD"
STRATEGIES: Dict[str, Dict[str, Any]] = {
    "squeeze_trend": {"primary_tf": 60, "context_tf": 1440, "control_p90_r": 0.315,
                      "lab_test_expectancy_r": 0.381, "lab_train_expectancy_r": -0.28},
}
MIN_FORWARD_TRADES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load(db: Session, tf: str, n: int) -> list:
    from services.signal_cycle import load_candles
    return load_candles(db, SYMBOL, tf, n)


def _prepared(db: Session, now: datetime):
    """H1 primary + D1 context (resampled from H4), cleaned like the lab."""
    from strategy.data_quality import clean_candles
    from strategy.engine import attach_context, prepare_context, prepare_primary
    from strategy.lab import default_cfg
    from strategy.research import resample

    cfg = default_cfg(60, 1440)
    h1, rep = clean_candles(_load(db, "60", 700), 60, now)
    h4, _ = clean_candles(_load(db, "240", 1800), 240, now)
    if len(h1) < cfg.min_history_bars + 110 or h4.empty:
        return None, cfg, rep
    d1, _ = clean_candles(resample(h4, 1440), 1440, now)
    return attach_context(prepare_primary(h1, cfg), prepare_context(d1, cfg)), cfg, rep


def run(db: Session, now: Optional[datetime] = None, fetch: bool = True,
        fetch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Evaluate every shadow strategy on the last closed H1 bar and store BUY/SELL decisions."""
    from strategy.config import RiskConfig
    from strategy import vol_lab

    now = now or _now()
    if fetch:
        if fetch_fn is None:
            from services.market_service import fetch_and_store as fetch_fn
        try:
            fetch_fn(db, SYMBOL, "60", limit=5)   # the bar that just closed
        except Exception:
            db.rollback()
    p, cfg, rep = _prepared(db, now)
    if p is None:
        return {"status": "insufficient_data"}
    i = len(p) - 1
    bar_close = p["close_time"].iloc[i].to_pydatetime()
    if now - bar_close > timedelta(minutes=90):
        return {"status": "stale_data", "last_bar_close": bar_close.isoformat()}

    out = {}
    for name in STRATEGIES:
        d = vol_lab.CANDIDATES[name][1](p, cfg, RiskConfig())(i) or {}
        action = d.get("action")
        if action not in ("BUY", "SELL"):
            out[name] = {"action": "NO TRADE", "reasons": d.get("reason_codes")}
            continue
        busy = (db.query(ShadowSignal).filter(ShadowSignal.strategy == name, ShadowSignal.symbol == SYMBOL,
                                              ShadowSignal.status == "open").first())
        if busy is not None:
            out[name] = {"action": action, "skipped": f"position #{busy.id} still open (one at a time, as in backtest)"}
            continue
        row = ShadowSignal(strategy=name, symbol=SYMBOL, timeframe="60", signal_type=action, bar_close=bar_close,
                           entry=float(d["entry"]), stop_loss=float(d["stop_loss"]), take_profit=float(d["take_profit"]),
                           atr=float(p["atr"].iloc[i]), regime=d.get("regime"),
                           context_trend=str(p["c_trend"].iloc[i]),
                           details=json.dumps({"bar_open": str(p["timestamp"].iloc[i])}))
        db.add(row)
        try:
            db.commit()
        except IntegrityError:   # same bar already recorded (rerun / restart)
            db.rollback()
            out[name] = {"action": action, "duplicate": True}
            continue
        log.info("Shadow %s: %s @ %.2f SL %.2f TP %.2f", name, action, row.entry, row.stop_loss, row.take_profit)
        out[name] = {"action": action, "id": row.id}
    return {"status": "ok", "bar_close": bar_close.isoformat(), "strategies": out}


def resolve(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Walk open shadow positions over stored H1 bars with the backtest's fill/exit rules."""
    from paper.broker import Position, process
    from strategy.config import RiskConfig, StrategyConfig
    from strategy.data_quality import clean_candles

    now = now or _now()
    rows: List[ShadowSignal] = db.query(ShadowSignal).filter(ShadowSignal.status == "open").all()
    if not rows:
        return {"status": "idle"}
    start = min(r.bar_close for r in rows) - timedelta(hours=2)
    from models.candle import Candle
    raw = [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume, "timestamp": c.timestamp}
           for c in db.query(Candle).filter(Candle.symbol == SYMBOL, Candle.timeframe == "60",
                                            Candle.timestamp >= start).order_by(Candle.timestamp.asc()).all()]
    df, _ = clean_candles(raw, 60, now)
    bars = df.to_dict("records") if not df.empty else []
    max_hold = timedelta(hours=StrategyConfig().max_hold_bars)   # 48 H1 bars, counted in trading bars
    done = 0
    for r in rows:
        pos = Position(direction=r.signal_type, status="PENDING", signal_time=r.bar_close,
                       expires_at=r.bar_close + timedelta(minutes=60),   # must fill on the very next bar
                       entry_ref=r.entry, zone_low=float("-inf"), zone_high=float("inf"),
                       stop_loss=r.stop_loss, take_profit=r.take_profit,
                       risk_per_oz=abs(r.entry - r.stop_loss), lots=0.01)
        pos = process(pos, bars, RiskConfig(), 60, max_hold, max_gap=timedelta(hours=3))
        if pos.status not in ("CLOSED", "CANCELLED"):
            continue
        filled = pos.fill_price is not None
        r.status = "closed" if pos.status == "CLOSED" else "not_filled"
        r.outcome, r.outcome_r = pos.exit_reason, pos.r_multiple
        r.mfe_r = round(pos.mfe_r, 3) if filled else None
        r.mae_r = round(pos.mae_r, 3) if filled else None
        r.fill_price, r.fill_time, r.exit_price, r.exit_time = pos.fill_price, pos.fill_time, pos.exit_price, pos.exit_time
        r.data_gap, r.resolved_at = pos.data_gap, now
        done += 1
    db.commit()
    return {"status": "ok", "resolved": done, "open": len(rows) - done}


def performance(db: Session, strategy: str = "squeeze_trend") -> Dict[str, Any]:
    from services.signal_outcomes import summarize
    meta = STRATEGIES.get(strategy, {})
    rows: List[ShadowSignal] = (db.query(ShadowSignal).filter(ShadowSignal.strategy == strategy)
                                .order_by(ShadowSignal.bar_close.asc()).all())
    closed = [r for r in rows if r.status == "closed" and r.outcome_r is not None]
    s = summarize([r.outcome_r for r in closed], [r.mfe_r for r in closed])
    ci = s.get("ci95_r")
    checks = {
        "forward_trades_ge_30": s["trades"] >= MIN_FORWARD_TRADES,
        "ci95_low_gt_0": bool(ci and ci[0] > 0),
        "beats_random_control_p90": s.get("expectancy_r") is not None and s["expectancy_r"] > meta.get("control_p90_r", 9),
    }
    first = rows[0].bar_close if rows else None
    return {
        "strategy": strategy, "lab": meta, "started": first.isoformat() if first else None,
        "signals": len(rows), "open": sum(r.status == "open" for r in rows),
        "not_filled": sum(r.status == "not_filled" for r in rows),
        "forward": s, "acceptance": {"checks": checks, "passed": all(checks.values()),
                                     "progress": f"{s['trades']}/{MIN_FORWARD_TRADES}"},
        "trades": [{"id": r.id, "side": r.signal_type, "bar_close": r.bar_close.isoformat(), "entry": r.entry,
                    "stop_loss": r.stop_loss, "take_profit": r.take_profit, "status": r.status,
                    "outcome": r.outcome, "r": r.outcome_r, "mfe_r": r.mfe_r,
                    "exit_time": r.exit_time.isoformat() if r.exit_time else None} for r in rows[-100:]],
    }
