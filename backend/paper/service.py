"""
Paper-trading service (DB side). Virtual account only.

  submit_signal(db, signal)  BUY/SELL → PENDING paper trade (idempotent per signal_key)
  tick(db, now)              process closed M5 bars for PENDING/OPEN trades
  health(db)                 strategy health from closed paper trades
  stats(db)                  account + performance summary

Account-level limits (paper mirrors what live would require):
  max open positions, daily loss limit, max drawdown from peak → HALT new entries.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.paper import PaperAccount, PaperTrade
from paper.broker import Position, process
from strategy.config import RiskConfig

log = logging.getLogger(__name__)

ACCOUNT = "paper-default"
BAR_TF = "5"
BAR_MINUTES = 5


def _cfg() -> Dict[str, float]:
    f = lambda k, d: float(os.getenv(k, d))  # noqa: E731
    return {"enabled": os.getenv("PAPER_TRADING_ENABLED", "true").lower() in ("1", "true", "yes"),
            "start_balance": f("PAPER_START_BALANCE", 10000), "max_open": int(f("PAPER_MAX_OPEN", 1)),
            "daily_loss_pct": f("PAPER_DAILY_LOSS_PCT", 2.0), "max_dd_pct": f("PAPER_MAX_DD_PCT", 10.0)}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def account(db: Session) -> PaperAccount:
    acc = db.query(PaperAccount).filter(PaperAccount.name == ACCOUNT).first()
    if acc is None:
        b = _cfg()["start_balance"]
        acc = PaperAccount(name=ACCOUNT, mode="paper", start_balance=b, balance=b, peak_balance=b)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    if acc.mode != "paper":  # defensive: this service must never touch anything else
        raise RuntimeError("paper service refused a non-paper account")
    return acc


def _closed(db: Session, acc: PaperAccount) -> List[PaperTrade]:
    return (db.query(PaperTrade).filter(PaperTrade.account_id == acc.id, PaperTrade.status == "CLOSED")
            .order_by(PaperTrade.exit_time.asc()).all())


def health(db: Session) -> Dict[str, Any]:
    from strategy import health as h, registry
    try:
        acc = account(db)
        rs = [t.r_multiple for t in _closed(db, acc) if t.r_multiple is not None]
    except Exception:  # no tables yet / DB issue: health unknown, do not block on it
        db.rollback()
        return {"status": "INSUFFICIENT_DATA", "trades": 0, "risk_multiplier": 1.0, "reasons": ["paper ledger unavailable"]}
    return h.evaluate(rs, registry.active_reference()).to_dict()


def _limits_block(db: Session, acc: PaperAccount, cfg: Dict[str, float], now: datetime) -> Optional[str]:
    active = db.query(PaperTrade).filter(PaperTrade.account_id == acc.id,
                                         PaperTrade.status.in_(["PENDING", "OPEN"])).count()
    if active >= cfg["max_open"]:
        return f"MAX_OPEN_POSITIONS_{int(cfg['max_open'])}"
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = sum(t.pnl_usd or 0 for t in _closed(db, acc) if t.exit_time and t.exit_time >= day0)
    if today <= -cfg["daily_loss_pct"] / 100 * acc.balance:
        return "DAILY_LOSS_LIMIT"
    if acc.peak_balance and (acc.peak_balance - acc.balance) / acc.peak_balance * 100 >= cfg["max_dd_pct"]:
        acc.halted, acc.halt_reason = True, f"Max drawdown {cfg['max_dd_pct']}% reached"
        db.commit()
    if acc.halted:
        return f"ACCOUNT_HALTED: {acc.halt_reason}"
    return None


def submit_signal(db: Session, sig: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    cfg = _cfg()
    if not cfg["enabled"]:
        return {"status": "disabled"}
    from strategy.live import position_size
    now = now or _now()
    acc = account(db)
    blocked = _limits_block(db, acc, cfg, now)
    if blocked:
        return {"status": "rejected", "reason": blocked}
    d = sig["decision"]
    rc = RiskConfig()
    hm = (sig.get("strategy_health") or {}).get("risk_multiplier", 1.0) or 1.0
    from dataclasses import replace
    pos = position_size(acc.balance, d["risk"] + (d.get("cost") or 0) / 2, replace(rc, risk_pct=rc.risk_pct * hm))
    if not pos.get("lots"):
        return {"status": "rejected", "reason": "SIZE_BELOW_MIN_LOT"}
    key = f"{sig['instrument']}|{sig['primary_tf']}|{d['bar_close']}|{d['action']}|{sig['config_hash']}"
    row = PaperTrade(
        account_id=acc.id, signal_key=key, signal_id=sig.get("id"), strategy="trend_pullback",
        strategy_version=sig["strategy_version"], config_hash=sig["config_hash"], direction=d["action"],
        status="PENDING", regime=d.get("regime"),
        signal_time=datetime.fromisoformat(d["bar_close"]), expires_at=datetime.fromisoformat(d["expires_at"]),
        entry_ref=d["entry"], zone_low=d["entry_zone"]["low"], zone_high=d["entry_zone"]["high"],
        stop_loss=d["stop_loss"], take_profit=d["take_profit"], risk_per_oz=d["risk"], lots=pos["lots"],
        spread=rc.spread, slippage=rc.slippage,
        reasons=json.dumps({"reasons": d.get("reasons"), "score": d.get("signal_score"),
                            "components": d.get("score_components"), "metrics": d.get("metrics")}, ensure_ascii=False))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:  # same signal already submitted (restart, manual + scheduler run)
        db.rollback()
        return {"status": "duplicate", "signal_key": key}
    return {"status": "pending", "paper_trade_id": row.id, "lots": pos["lots"], "signal_key": key}


def _to_pos(t: PaperTrade) -> Position:
    return Position(direction=t.direction, status=t.status, signal_time=t.signal_time, expires_at=t.expires_at,
                    entry_ref=t.entry_ref, zone_low=t.zone_low, zone_high=t.zone_high, stop_loss=t.stop_loss,
                    take_profit=t.take_profit, risk_per_oz=t.risk_per_oz, lots=t.lots, fill_price=t.fill_price,
                    fill_time=t.fill_time, mfe_r=t.mfe_r or 0.0, mae_r=t.mae_r or 0.0,
                    bars_processed=t.bars_processed or 0, last_bar=t.last_bar, data_gap=bool(t.data_gap),
                    open_minutes=t.open_minutes or 0)


def tick(db: Session, now: Optional[datetime] = None, fetch: bool = True, fetch_fn=None) -> Dict[str, Any]:
    """Advance PENDING/OPEN trades with closed M5 bars. Stale data → nothing is assumed."""
    from services.signal_cycle import load_candles
    from strategy.config import StrategyConfig
    from strategy.data_quality import clean_candles

    if not _cfg()["enabled"]:
        return {"status": "disabled"}
    now = now or _now()
    acc = account(db)
    active = db.query(PaperTrade).filter(PaperTrade.account_id == acc.id,
                                         PaperTrade.status.in_(["PENDING", "OPEN"])).all()
    if not active:
        return {"status": "idle"}
    if fetch:
        if fetch_fn is None:
            from services.market_service import fetch_and_store as fetch_fn
        try:
            fetch_fn(db, "XAUUSD", BAR_TF, limit=100)
        except Exception:
            db.rollback()
    bars, rep = clean_candles(load_candles(db, "XAUUSD", BAR_TF, 3000), BAR_MINUTES, now)
    if bars.empty:
        return {"status": "no_data"}
    age = rep.age_minutes or 0
    records = bars.to_dict("records")
    rc = RiskConfig()
    cfg = StrategyConfig()
    max_hold = timedelta(minutes=cfg.max_hold_bars * cfg.primary_tf)
    changed = []
    for t in active:
        pos = process(_to_pos(t), records, RiskConfig(spread=t.spread, slippage=t.slippage,
                                                      commission_per_lot=rc.commission_per_lot,
                                                      swap_long=rc.swap_long, swap_short=rc.swap_short,
                                                      contract_size=rc.contract_size), BAR_MINUTES, max_hold)
        for k in ("status", "fill_price", "fill_time", "exit_price", "exit_time", "exit_reason", "r_multiple",
                  "pnl_usd", "costs_usd", "mfe_r", "mae_r", "bars_processed", "last_bar", "data_gap", "open_minutes"):
            setattr(t, k, getattr(pos, k))
        if pos.status == "CLOSED" and pos.pnl_usd is not None:
            acc.balance = round(acc.balance + pos.pnl_usd, 2)
            acc.peak_balance = max(acc.peak_balance, acc.balance)
        changed.append({"id": t.id, "status": t.status, "exit_reason": t.exit_reason, "r": t.r_multiple})
    db.commit()
    stale = age > 3 * BAR_MINUTES
    if stale:
        log.warning("Paper tick: M5 data is %.0f min old — positions only advanced to the last closed bar", age)
    return {"status": "stale_data" if stale else "ok", "data_age_minutes": age, "trades": changed}


def stats(db: Session) -> Dict[str, Any]:
    acc = account(db)
    closed = _closed(db, acc)
    rs = np.array([t.r_multiple for t in closed if t.r_multiple is not None])
    out = {"account": {"name": acc.name, "mode": acc.mode, "start_balance": acc.start_balance,
                       "balance": acc.balance, "peak_balance": acc.peak_balance, "halted": acc.halted,
                       "halt_reason": acc.halt_reason},
           "trades": int(len(rs)),
           "open_or_pending": db.query(PaperTrade).filter(PaperTrade.account_id == acc.id,
                                                          PaperTrade.status.in_(["PENDING", "OPEN"])).count(),
           "cancelled": db.query(PaperTrade).filter(PaperTrade.account_id == acc.id,
                                                    PaperTrade.status == "CANCELLED").count()}
    first = db.query(PaperTrade).filter(PaperTrade.account_id == acc.id).order_by(PaperTrade.created_at.asc()).first()
    out["days"] = (_now() - first.created_at).days if first else 0
    if len(rs):
        boot = np.random.default_rng(1).choice(rs, size=(2000, len(rs))).mean(axis=1)
        out.update({"win_rate": round(float((rs > 0).mean() * 100), 1),
                    "expectancy_r": round(float(rs.mean()), 3),
                    "expectancy_r_ci95": [round(float(np.percentile(boot, 2.5)), 3),
                                          round(float(np.percentile(boot, 97.5)), 3)],
                    "total_pnl_usd": round(float(sum(t.pnl_usd or 0 for t in closed)), 2),
                    "total_costs_usd": round(float(sum(t.costs_usd or 0 for t in closed)), 2),
                    "data_gap_trades": sum(1 for t in closed if t.data_gap)})
    else:
        out["note"] = "Hali yopilgan paper savdo yo'q — natija haqida xulosa qilib bo'lmaydi"
    return out


def trades_for_analysis(db: Session) -> List[Dict[str, Any]]:
    from strategy.run_lab import session
    acc = account(db)
    out = []
    for t in _closed(db, acc):
        out.append({"r": t.r_multiple, "mfe_r": t.mfe_r, "mae_r": t.mae_r, "regime": t.regime,
                    "direction": t.direction, "exit_reason": t.exit_reason,
                    "session": session(str(t.signal_time)),
                    "cost_r": (t.costs_usd or 0) / (t.risk_per_oz * 100 * t.lots) if t.lots else 0.0})
    return out
