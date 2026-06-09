"""
Historical pattern analysis for forecast enrichment.
- monthly_seasonality: XAU/USD average % change for a given calendar month
- event_impact_analysis: avg price move before/after NFP/CPI/FOMC events
- zone_test_analysis: how many times price has tested a S/R zone and bounce vs break rate
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from models.candle import Candle
from models.economic_calendar import EconomicEvent

log = logging.getLogger(__name__)


def monthly_seasonality(db: Session, symbol: str, month: int) -> Dict[str, Any]:
    """
    For the given calendar month (1–12), query daily candles (tf='1440'),
    group by year, compute monthly % change per year.
    Returns seasonality stats or {"insufficient_data": True}.
    """
    try:
        rows = (
            db.query(Candle)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == "1440",
                func.extract("month", Candle.timestamp) == month,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )

        if not rows:
            return {"insufficient_data": True}

        by_year: Dict[int, List[Candle]] = {}
        for row in rows:
            year = row.timestamp.year
            by_year.setdefault(year, []).append(row)

        if len(by_year) < 2:
            return {"insufficient_data": True}

        changes: List[float] = []
        highs_pct: List[float] = []
        lows_pct: List[float] = []

        for year_rows in by_year.values():
            year_rows_sorted = sorted(year_rows, key=lambda r: r.timestamp)
            first_open  = float(year_rows_sorted[0].open)
            last_close  = float(year_rows_sorted[-1].close)
            month_high  = max(float(r.high) for r in year_rows_sorted)
            month_low   = min(float(r.low)  for r in year_rows_sorted)

            if first_open == 0:
                continue

            chg = (last_close - first_open) / first_open * 100
            changes.append(chg)
            highs_pct.append((month_high  - first_open) / first_open * 100)
            lows_pct.append( (month_low   - first_open) / first_open * 100)

        if len(changes) < 2:
            return {"insufficient_data": True}

        positive = sum(1 for c in changes if c > 0)
        negative = len(changes) - positive
        avg_chg  = round(sum(changes) / len(changes), 2)
        win_rate = round(positive / len(changes) * 100, 1)
        avg_high = round(sum(highs_pct) / len(highs_pct), 2)
        avg_low  = round(sum(lows_pct)  / len(lows_pct),  2)

        direction = "ko'tariladi" if avg_chg > 0 else "tushadi"
        note = (
            f"{month}-oyda XAUUSD tarixan o'rtacha {avg_chg:+.2f}% {direction}. "
            f"Win rate: {win_rate:.0f}% ({positive}/{len(changes)} yil)."
        )

        return {
            "month":            month,
            "years_analyzed":   len(changes),
            "avg_change_pct":   avg_chg,
            "positive_months":  positive,
            "negative_months":  negative,
            "win_rate_pct":     win_rate,
            "avg_high_pct":     avg_high,
            "avg_low_pct":      avg_low,
            "note":             note,
        }
    except Exception as exc:
        log.warning("monthly_seasonality error: %s", exc)
        return {"insufficient_data": True}


def event_impact_analysis(db: Session, symbol: str, event_keywords: List[str]) -> Dict[str, Any]:
    """
    Find EconomicEvent rows matching any of the keywords, then measure
    price move 4h before and 24h after each event using H1 candles.
    Returns impact stats or {"insufficient_data": True}.
    """
    try:
        filters = [EconomicEvent.event.ilike(f"%{kw}%") for kw in event_keywords]
        from sqlalchemy import or_
        events = (
            db.query(EconomicEvent)
            .filter(or_(*filters))
            .order_by(EconomicEvent.event_time.asc())
            .all()
        )

        if len(events) < 3:
            return {"insufficient_data": True}

        pre_moves:  List[float] = []
        post_moves: List[float] = []

        for ev in events:
            et = ev.event_time
            pre_time  = et - timedelta(hours=4)
            post_time = et + timedelta(hours=24)

            def _close_near(ts: datetime) -> Optional[float]:
                row = (
                    db.query(Candle)
                    .filter(
                        Candle.symbol    == symbol,
                        Candle.timeframe == "60",
                        Candle.timestamp >= ts - timedelta(hours=2),
                        Candle.timestamp <= ts + timedelta(hours=2),
                    )
                    .order_by(func.abs(func.strftime("%s", Candle.timestamp) - func.strftime("%s", ts)))
                    .first()
                )
                return float(row.close) if row else None

            pre_close  = _close_near(pre_time)
            at_close   = _close_near(et)
            post_close = _close_near(post_time)

            if pre_close and at_close:
                pre_moves.append(at_close - pre_close)
            if at_close and post_close:
                post_moves.append(post_close - at_close)

        if len(pre_moves) < 3:
            return {"insufficient_data": True}

        avg_pre  = round(sum(pre_moves)  / len(pre_moves),  2)
        avg_post = round(sum(post_moves) / len(post_moves), 2) if post_moves else 0.0
        bull_after = sum(1 for m in post_moves if m > 0)
        bear_after = len(post_moves) - bull_after
        bull_pct = round(bull_after / len(post_moves) * 100, 1) if post_moves else 0.0
        bear_pct = round(bear_after / len(post_moves) * 100, 1) if post_moves else 0.0

        note = (
            f"{len(pre_moves)} ta voqea tahlil qilindi. "
            f"Voqeadan 4s oldin o'rtacha harakat: {avg_pre:+.2f}$. "
            f"Voqeadan 24s keyin: {avg_post:+.2f}$ ({bull_pct:.0f}% bullish)."
        )

        return {
            "events_analyzed":    len(pre_moves),
            "avg_pre_4h_move":    avg_pre,
            "avg_post_24h_move":  avg_post,
            "bullish_after_pct":  bull_pct,
            "bearish_after_pct":  bear_pct,
            "note":               note,
        }
    except Exception as exc:
        log.warning("event_impact_analysis error: %s", exc)
        return {"insufficient_data": True}


def zone_test_analysis(
    db: Session,
    symbol: str,
    zone_price: float,
    tolerance_pct: float = 0.003,
) -> Dict[str, Any]:
    """
    In the last 90 days of H1 candles, find all candles whose range touches zone_price.
    Classify each touch as bounce (close moved away) or break (close crossed zone).
    """
    try:
        since = datetime.utcnow() - timedelta(days=90)
        upper_band = zone_price * (1 + tolerance_pct)
        lower_band = zone_price * (1 - tolerance_pct)

        rows = (
            db.query(Candle)
            .filter(
                Candle.symbol    == symbol,
                Candle.timeframe == "60",
                Candle.timestamp >= since,
                Candle.low  <= upper_band,
                Candle.high >= lower_band,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )

        if not rows:
            return {
                "zone_price":      round(zone_price, 4),
                "touches":         0,
                "bounces":         0,
                "breaks":          0,
                "bounce_rate_pct": 0.0,
                "last_touch_date": None,
                "note":            "Zona sinovi topilmadi (90 kun).",
            }

        bounces = 0
        breaks  = 0
        for r in rows:
            close     = float(r.close)
            move_away = abs(close - zone_price) / zone_price
            if move_away > 0.002:
                bounces += 1
            else:
                breaks += 1

        total       = len(rows)
        bounce_rate = round(bounces / total * 100, 1) if total else 0.0
        last_touch  = rows[-1].timestamp.strftime("%Y-%m-%d %H:%M") if rows else None

        note = (
            f"Zona ${zone_price:.2f}: oxirgi 90 kunda {total} marta sinaldi. "
            f"Qaytish: {bounce_rate:.0f}% ({bounces}/{total})."
        )

        return {
            "zone_price":      round(zone_price, 4),
            "touches":         total,
            "bounces":         bounces,
            "breaks":          breaks,
            "bounce_rate_pct": bounce_rate,
            "last_touch_date": last_touch,
            "note":            note,
        }
    except Exception as exc:
        log.warning("zone_test_analysis error: %s", exc)
        return {
            "zone_price":      round(zone_price, 4),
            "touches":         0,
            "bounces":         0,
            "breaks":          0,
            "bounce_rate_pct": 0.0,
            "last_touch_date": None,
            "note":            "Tahlil xatosi.",
        }
