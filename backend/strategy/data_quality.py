"""
Candle cleaning and validation.

Problems this module handles (all observed in the project's real data):
  * the last candle returned by the provider is still forming (repaints);
  * Twelvedata emits flat "filler" candles while the market is closed at the
    weekend (range ≈ $0.25), which distort ATR/RSI/ADX;
  * the ``candles`` table contains a second, foreign price series interleaved
    with the real one (≈$2 300 vs ≈$4 000 at the same dates);
  * duplicate / unsorted / invalid OHLC rows, stale data and gaps.

Timestamps are bar OPEN times in naive UTC (the convention used by
``market_service``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

# Status codes, ordered by severity
OK = "OK"
MARKET_CLOSED = "MARKET_CLOSED"
STALE = "STALE"
INSUFFICIENT = "INSUFFICIENT_DATA"
UNRELIABLE = "UNRELIABLE_DATA"


@dataclass
class DataQualityReport:
    timeframe: int
    status: str = OK
    issues: List[str] = field(default_factory=list)
    rows_in: int = 0
    rows_out: int = 0
    dropped_invalid: int = 0
    dropped_duplicates: int = 0
    dropped_forming: int = 0
    dropped_weekend: int = 0
    dropped_foreign: int = 0
    gaps_in_window: int = 0
    last_closed_bar_open: Optional[str] = None
    last_closed_bar_close: Optional[str] = None
    age_minutes: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _utc_naive(ts: datetime) -> datetime:
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def to_frame(candles: Iterable[Any]) -> pd.DataFrame:
    """Accept list of dicts / ORM rows / DataFrame and return a typed frame."""
    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        rows = []
        for c in candles:
            get = c.get if isinstance(c, dict) else (lambda k, _c=c: getattr(_c, k, None))
            rows.append({k: get(k) for k in ("timestamp", "open", "high", "low", "close", "volume")})
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.tz_localize(None)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["volume"] = df["volume"].fillna(0.0)
    return df


def is_market_closed(ts: datetime) -> bool:
    """Approximate spot-gold weekend closure: Fri 21:00 → Sun 22:00 UTC."""
    dow, hour = ts.weekday(), ts.hour
    if dow == 5:
        return True
    if dow == 4 and hour >= 21:
        return True
    if dow == 6 and hour < 22:
        return True
    return False


def _foreign_series_mask(df: pd.DataFrame, max_jump: float) -> np.ndarray:
    """
    Walk backwards from the newest bar. A bar is accepted only if its close is
    within ``max_jump`` (fraction) of the open of the last accepted (newer) bar.
    The newest bar itself must agree with the median of the last 20 closes.
    Returns a boolean mask of rows to DROP.
    """
    n = len(df)
    drop = np.zeros(n, dtype=bool)
    if n == 0:
        return drop
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()

    tail_median = float(np.median(closes[-20:]))
    start = n - 1
    while start >= 0 and abs(closes[start] / tail_median - 1) > max_jump:
        drop[start] = True
        start -= 1
    if start < 0:
        return drop

    ref = opens[start]
    for i in range(start - 1, -1, -1):
        if abs(closes[i] / ref - 1) > max_jump:
            drop[i] = True
        else:
            ref = opens[i]
    return drop


def clean_candles(
    candles: Iterable[Any],
    timeframe_minutes: int,
    now: Optional[datetime] = None,
    drop_forming: bool = True,
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Return (clean_frame, report). ``now`` defaults to current UTC time."""
    tf = int(timeframe_minutes)
    report = DataQualityReport(timeframe=tf)
    df = to_frame(candles)
    report.rows_in = len(df)
    if df.empty:
        report.status = INSUFFICIENT
        report.issues.append("NO_DATA")
        return df, report

    # 1. invalid values / OHLC consistency
    vals = df[["open", "high", "low", "close"]]
    finite = np.isfinite(vals.to_numpy()).all(axis=1) & (vals > 0).all(axis=1).to_numpy()
    finite &= df["timestamp"].notna().to_numpy()
    body_hi = df[["open", "close"]].max(axis=1)
    body_lo = df[["open", "close"]].min(axis=1)
    consistent = ((df["high"] >= body_hi) & (df["low"] <= body_lo)).to_numpy()
    keep = finite & consistent
    report.dropped_invalid = int((~keep).sum())
    df = df[keep]

    # 2. sort + dedup (keep latest write)
    before = len(df)
    df = df.sort_values("timestamp", kind="stable").drop_duplicates("timestamp", keep="last")
    report.dropped_duplicates = before - len(df)

    # 3. forming bar
    now = _utc_naive(now or datetime.now(timezone.utc))
    if drop_forming and len(df):
        close_times = df["timestamp"] + pd.Timedelta(minutes=tf)
        forming = (close_times > pd.Timestamp(now)).to_numpy()
        report.dropped_forming = int(forming.sum())
        df = df[~forming]

    # 4. weekend filler candles (only meaningful intraday)
    if tf < 1440 and len(df):
        ts = df["timestamp"]
        rng = (df["high"] - df["low"]).to_numpy()
        closed = np.array([is_market_closed(t) for t in ts.to_numpy(dtype="datetime64[us]").astype(object)])
        ref_rng = float(np.median(rng[~closed])) if (~closed).any() else float(np.median(rng))
        flat = rng < 0.2 * ref_rng
        weekend_drop = (ts.dt.dayofweek.to_numpy() == 5) | (closed & flat)
        report.dropped_weekend = int(weekend_drop.sum())
        df = df[~weekend_drop]

    # 5. foreign / contaminated series
    if len(df):
        # daily bars from the provider are stamped 00:00 UTC; the foreign series uses 08:00
        foreign = np.zeros(len(df), dtype=bool)
        if tf >= 1440:
            t = df["timestamp"]
            foreign |= ((t.dt.hour != 0) | (t.dt.minute != 0)).to_numpy()
        max_jump = min(0.08, 0.04 * math.sqrt(max(tf, 1) / 60.0))
        keep_idx = np.flatnonzero(~foreign)
        sub = _foreign_series_mask(df.iloc[keep_idx], max_jump)
        foreign[keep_idx[sub]] = True
        report.dropped_foreign = int(foreign.sum())
        df = df[~foreign]

    df = df.reset_index(drop=True)
    report.rows_out = len(df)
    if df.empty:
        report.status = INSUFFICIENT
        report.issues.append("NO_VALID_ROWS")
        return df, report

    # 6. gaps (excluding weekend closures) in the last 300 bars
    window = df.tail(300)
    if tf < 1440 and len(window) > 1:
        gaps = 0
        prev = None
        for t in window["timestamp"].to_numpy(dtype="datetime64[us]").astype(object):
            if prev is not None and (t - prev) > timedelta(minutes=tf * 1.5):
                probe, weekend = prev + timedelta(minutes=tf), False
                while probe < t:
                    if is_market_closed(probe):
                        weekend = True
                        break
                    probe += timedelta(minutes=tf)
                # the daily 1-hour maintenance break (21–22 UTC) is normal
                if not weekend and (t - prev) > timedelta(minutes=max(tf * 1.5, 120)):
                    gaps += 1
            prev = t
        report.gaps_in_window = gaps

    last_open = df["timestamp"].iloc[-1].to_pydatetime()
    last_close = last_open + timedelta(minutes=tf)
    report.last_closed_bar_open = last_open.isoformat()
    report.last_closed_bar_close = last_close.isoformat()
    report.age_minutes = round((now - last_close).total_seconds() / 60.0, 1)

    if report.dropped_foreign:
        report.issues.append(f"FOREIGN_SERIES_ROWS_DROPPED:{report.dropped_foreign}")
    if report.dropped_invalid:
        report.issues.append(f"INVALID_ROWS_DROPPED:{report.dropped_invalid}")
    if report.gaps_in_window:
        report.issues.append(f"GAPS_IN_WINDOW:{report.gaps_in_window}")
    return df, report


def assess(
    report: DataQualityReport,
    now: datetime,
    min_bars: int,
    max_stale_bars: float,
    max_gaps: int,
) -> DataQualityReport:
    """Set ``report.status`` for live use (staleness, history, gaps)."""
    now = _utc_naive(now)
    if report.status != OK:
        return report
    if report.rows_out < min_bars:
        report.status = INSUFFICIENT
        report.issues.append(f"HISTORY_{report.rows_out}_LT_{min_bars}")
        return report
    if is_market_closed(now):
        report.status = MARKET_CLOSED
        report.issues.append("MARKET_CLOSED")
        return report
    if report.age_minutes is not None and report.age_minutes > max_stale_bars * report.timeframe:
        report.status = STALE
        report.issues.append(f"STALE_{report.age_minutes:.0f}MIN")
        return report
    if report.gaps_in_window > max_gaps:
        report.status = UNRELIABLE
        report.issues.append("TOO_MANY_GAPS")
    return report
