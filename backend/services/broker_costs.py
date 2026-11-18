"""
Broker cost calibration from the MetaTrader feed.

The backtest, paper broker and position sizing use ``RiskConfig`` cost
assumptions (spread $0.30, slippage $0.10, swap 0 = unknown). This module stores
the real broker's per-minute spreads and financing and reports how far the
assumptions are from reality — overall, by UTC hour, around high-impact USD news
and at the daily rollover — plus the env overrides that would apply them.
Nothing is changed automatically: costs feed every result, so the owner decides.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.broker import BrokerQuote

log = logging.getLogger(__name__)

NEWS_WINDOW = timedelta(minutes=15)
FIELDS = ("bid", "ask", "spread_min", "spread_avg", "spread_max", "ticks", "point", "digits", "contract_size",
          "swap_long", "swap_short", "swap_type", "swap_3day", "stop_level", "broker_symbol", "is_demo")


def _parse_ts(v: Any) -> datetime:
    """Unix seconds (what the EA sends), ISO-8601, or MetaTrader's 'YYYY.MM.DD HH:MM'."""
    if isinstance(v, (int, float)) or str(v).isdigit():
        return datetime.fromtimestamp(int(v), tz=timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    s = str(v).strip().replace("Z", "+00:00")
    if len(s) >= 10 and s[4] == "." and s[7] == ".":
        s = s[:4] + "-" + s[5:7] + "-" + s[8:]
    ts = datetime.fromisoformat(s)
    if ts.tzinfo:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.replace(second=0, microsecond=0)


def ingest(db: Session, quotes: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    stored = dup = bad = 0
    for q in quotes:
        try:
            bid, ask = float(q["bid"]), float(q["ask"])
            if bid <= 0 or ask < bid:
                raise ValueError("bad prices")
            row = BrokerQuote(broker=str(q.get("broker") or "unknown")[:80], server=str(q.get("server") or "unknown")[:80],
                              symbol=str(q["symbol"]).upper()[:20], ts=_parse_ts(q["ts"]),
                              **{k: q.get(k) for k in FIELDS if k not in ("bid", "ask")}, bid=bid, ask=ask)
        except (KeyError, TypeError, ValueError) as exc:
            bad += 1
            log.debug("broker quote rejected: %s (%s)", exc, q)
            continue
        db.add(row)
        try:
            db.commit()
            stored += 1
        except IntegrityError:
            db.rollback()
            dup += 1
    return {"stored": stored, "duplicates": dup, "rejected": bad}


def swap_per_oz(value: Optional[float], swap_type: Optional[int], point: Optional[float],
                contract_size: Optional[float], price: float) -> Optional[float]:
    """Broker swap → price units per 1 unit (oz) per night. Account currency assumed USD."""
    if value is None or swap_type is None:
        return None
    if swap_type == 0:                       # points
        return value * point if point else None
    if swap_type in (1, 3):                  # money per lot
        return value / contract_size if contract_size else None
    if swap_type == 2:                       # annual interest %
        return price * value / 100.0 / 360.0
    return None


def _pct(xs: List[float]) -> Dict[str, Optional[float]]:
    if not xs:
        return {"n": 0, "p50": None, "p90": None, "p99": None}
    a = np.asarray(xs, dtype=float)
    return {"n": int(a.size), "p50": round(float(np.percentile(a, 50)), 4),
            "p90": round(float(np.percentile(a, 90)), 4), "p99": round(float(np.percentile(a, 99)), 4)}


def costs(db: Session, symbol: str = "XAUUSD", days: int = 30, broker: Optional[str] = None) -> Dict[str, Any]:
    from models.economic_calendar import EconomicEvent
    from strategy.config import RiskConfig

    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(BrokerQuote).filter(BrokerQuote.symbol == symbol.upper(), BrokerQuote.ts >= since)
    if broker:
        q = q.filter(BrokerQuote.broker == broker)
    rows: List[BrokerQuote] = q.order_by(BrokerQuote.ts.asc()).all()
    rc = RiskConfig()
    out: Dict[str, Any] = {"symbol": symbol.upper(), "days": days, "minutes": len(rows),
                           "assumed": {"spread": rc.spread, "slippage": rc.slippage,
                                       "swap_long": rc.swap_long, "swap_short": rc.swap_short,
                                       "contract_size": rc.contract_size}}
    if not rows:
        out["note"] = "Broker ma'lumoti hali kelmagan — MetaTrader'da GoldAI_CostFeed EA'ni ishga tushiring"
        return out

    events = [e.event_time for e in db.query(EconomicEvent).filter(
        EconomicEvent.currency == "USD", EconomicEvent.impact >= 3,
        EconomicEvent.event_time >= since - NEWS_WINDOW).all()]

    def near_news(t: datetime) -> bool:
        return any(abs((t - e).total_seconds()) <= NEWS_WINDOW.total_seconds() for e in events)

    avg_all, by_hour = [], defaultdict(list)
    news, normal, rollover = [], [], []
    for r in rows:
        s = r.spread_avg if r.spread_avg is not None else (r.ask - r.bid)
        avg_all.append(s)
        by_hour[r.ts.hour].append(s)
        if 21 <= r.ts.hour < 23:
            rollover.append(s)
        elif near_news(r.ts):
            news.append(r.spread_max if r.spread_max is not None else s)
        else:
            normal.append(s)

    last = rows[-1]
    mid = (last.bid + last.ask) / 2
    sl = swap_per_oz(last.swap_long, last.swap_type, last.point, last.contract_size, mid)
    ss = swap_per_oz(last.swap_short, last.swap_type, last.point, last.contract_size, mid)
    spread_typical = _pct(normal or avg_all)
    out.update({
        "broker": last.broker, "server": last.server, "is_demo": last.is_demo, "broker_symbol": last.broker_symbol,
        "first": rows[0].ts.isoformat(), "last": last.ts.isoformat(),
        "spread": {"all": _pct(avg_all), "normal_hours": spread_typical, "rollover_21_23_utc": _pct(rollover),
                   "news_pm15min_max": _pct(news),
                   "by_utc_hour_p50": {h: round(float(np.median(v)), 4) for h, v in sorted(by_hour.items())}},
        "spec": {"contract_size": last.contract_size, "digits": last.digits, "point": last.point,
                 "stop_level": last.stop_level, "swap_type": last.swap_type, "swap_3day_weekday": last.swap_3day,
                 "swap_long_raw": last.swap_long, "swap_short_raw": last.swap_short,
                 "swap_long_per_oz_night": round(sl, 4) if sl is not None else None,
                 "swap_short_per_oz_night": round(ss, 4) if ss is not None else None},
    })
    p50 = spread_typical["p50"]
    suggestions = {}
    if p50 is not None:
        suggestions["GOLDAI_SPREAD"] = p50
    if sl is not None:
        suggestions["GOLDAI_SWAP_LONG"] = round(sl, 4)
    if ss is not None:
        suggestions["GOLDAI_SWAP_SHORT"] = round(ss, 4)
    if last.contract_size and abs(last.contract_size - rc.contract_size) > 1e-9:
        suggestions["GOLDAI_CONTRACT_SIZE"] = last.contract_size
    notes = []
    if len(rows) < 60 * 24 * 5:
        notes.append("5 savdo kunidan kam ma'lumot — xulosa uchun kamida 2 hafta yig'ing")
    if p50 is not None and p50 > rc.spread * 1.2:
        notes.append(f"Real spread (p50 {p50}) taxmindan ({rc.spread}) {p50 / rc.spread:.1f}× katta — backtest natijalari optimistik")
    if sl is not None and rc.swap_long == 0:
        notes.append(f"Swap taxminda 0 (noma'lum); broker'da long {sl:+.3f} $/oz/kecha")
    if out.get("is_demo"):
        notes.append("Demo hisob — real hisob spread'i farq qilishi mumkin")
    out["suggested_env"] = suggestions
    out["notes"] = notes
    return out
