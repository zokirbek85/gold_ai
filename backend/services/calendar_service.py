"""
Economic Calendar service.
Fetches real upcoming economic events from ForexFactory public JSON feed.
No synthetic/generated events — returns empty list if fetch fails.

Source: https://nfs.faireconomy.media  (free, no API key)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from models.economic_calendar import EconomicEvent

log = logging.getLogger(__name__)

_FF_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FF_NEXT_WEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

_IMPACT_MAP = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0, "Non-Economic": 0}

# Only track currencies that directly affect gold
_TRACKED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF"}


def _parse_ff_date(date_str: str) -> Optional[datetime]:
    """Parse ForexFactory date — supports ISO 8601 and legacy text formats."""
    if not date_str:
        return None
    try:
        # ISO 8601 with timezone: "2026-05-31T08:30:00-04:00"
        from datetime import timezone as tz
        import re
        # Strip timezone offset and parse as UTC
        clean = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str).replace("T", " ").strip()
        return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        # Legacy: "Jan 06 2024 1:30pm"
        for fmt in ("%b %d %Y %I:%M%p", "%b %d %Y %I%p", "%b %d %Y"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _fetch_ff(url: str) -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 GoldAI/1.0"})
        events_raw = resp.json()
    except Exception as exc:
        log.warning("ForexFactory fetch failed (%s): %s", url, exc)
        return []

    result = []
    for e in events_raw:
        currency = (e.get("country") or e.get("currency") or "").upper()
        if currency not in _TRACKED_CURRENCIES:
            continue
        impact_str = e.get("impact", "Low")
        impact = _IMPACT_MAP.get(impact_str, 1)
        if impact == 0:
            continue

        # Date field is ISO 8601: "2026-06-06T08:30:00-04:00"
        dt = _parse_ff_date(e.get("date", ""))
        if dt is None:
            continue

        result.append({
            "event":      (e.get("title") or e.get("name") or "Unknown Event")[:200],
            "currency":   currency,
            "impact":     impact,
            "forecast":   str(e.get("forecast") or ""),
            "previous":   str(e.get("previous") or ""),
            "actual":     e.get("actual") or None,
            "event_time": dt,
        })
    return result


def _fetch_real_calendar() -> List[Dict[str, Any]]:
    """Fetch this week + next week, sorted ascending."""
    events = _fetch_ff(_FF_THIS_WEEK) + _fetch_ff(_FF_NEXT_WEEK)
    # Deduplicate by event+time
    seen: set = set()
    unique = []
    for e in events:
        key = f"{e['event']}|{e['event_time']}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda x: x["event_time"])
    log.info("ForexFactory: fetched %d economic events", len(unique))
    return unique


def get_or_generate_events(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """Return events from DB (next 8 days) or fetch from ForexFactory."""
    now = datetime.utcnow()
    future = now + timedelta(days=8)
    rows = (
        db.query(EconomicEvent)
        .filter(EconomicEvent.event_time >= now)
        .filter(EconomicEvent.event_time <= future)
        .order_by(EconomicEvent.event_time.asc())
        .limit(limit)
        .all()
    )
    if len(rows) >= 3:
        return [
            {
                "id": r.id, "event": r.event, "currency": r.currency,
                "impact": r.impact, "forecast": r.forecast, "previous": r.previous,
                "actual": r.actual, "event_time": r.event_time,
            }
            for r in rows
        ]

    items = [i for i in _fetch_real_calendar() if i["event_time"] >= now]
    db_items = []
    for item in items[:limit]:
        existing = (
            db.query(EconomicEvent)
            .filter(EconomicEvent.event == item["event"])
            .filter(EconomicEvent.event_time == item["event_time"])
            .first()
        )
        if existing:
            db_items.append({"id": existing.id, **item})
            continue
        e = EconomicEvent(
            event=item["event"], currency=item["currency"], impact=item["impact"],
            forecast=item["forecast"], previous=item["previous"],
            actual=item["actual"], event_time=item["event_time"],
        )
        db.add(e)
        db.flush()
        db_items.append({"id": e.id, **item})
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to save calendar events")
    return db_items[:limit]


def get_aggregate_score(db: Session, hours: int = 48) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    future = datetime.utcnow() + timedelta(hours=hours)
    rows = (
        db.query(EconomicEvent)
        .filter(EconomicEvent.event_time >= cutoff)
        .filter(EconomicEvent.event_time <= future)
        .all()
    )
    if not rows:
        return {"direction": "neutral", "score": 50.0, "avg_impact": 0.0, "event_count": 0}

    total = len(rows)
    avg_impact = sum(r.impact for r in rows) / total
    high_usd = sum(1 for r in rows if r.impact == 3 and r.currency == "USD")
    score = round(min(100.0, 50.0 + high_usd * 5), 1)

    return {
        "direction": "neutral",
        "score": score,
        "avg_impact": round(avg_impact, 1),
        "event_count": total,
    }


def refresh_calendar(db: Session) -> None:
    try:
        now = datetime.utcnow()
        db.query(EconomicEvent).filter(EconomicEvent.event_time < now).delete()
        items = [i for i in _fetch_real_calendar() if i["event_time"] >= now]
        for item in items:
            existing = (
                db.query(EconomicEvent)
                .filter(EconomicEvent.event == item["event"])
                .filter(EconomicEvent.event_time == item["event_time"])
                .first()
            )
            if not existing:
                db.add(EconomicEvent(
                    event=item["event"], currency=item["currency"], impact=item["impact"],
                    forecast=item["forecast"], previous=item["previous"],
                    actual=item["actual"], event_time=item["event_time"],
                ))
        db.commit()
        log.info("Calendar refreshed: %d upcoming events", len(items))
    except Exception:
        log.exception("Failed to refresh calendar")
        db.rollback()
