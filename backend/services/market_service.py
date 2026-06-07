"""
Market data service.

Priority:
  1. Twelvedata REST API  (real, always fresh)
  2. yfinance             (free fallback, sometimes rate-limited)
  3. Return []            — no synthetic data

Range → auto-selects interval + outputsize for Twelvedata:
  "1h"  → M1   candles  (60 bars)
  "4h"  → M1   candles  (240 bars)
  "1d"  → M5   candles  (288 bars)
  "1w"  → M15  candles  (672 bars)
  "1m"  → H1   candles  (720 bars)
  "3m"  → H4   candles  (540 bars)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

log = logging.getLogger(__name__)

# ── Symbol maps ───────────────────────────────────────────────────────────────

TD_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "XAU/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "BTCUSD": "BTC/USD",
}

YF_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "BTCUSD": "BTC-USD",
}

# Timeframe minutes string → Twelvedata interval string
TF_TO_TD: Dict[str, str] = {
    "1": "1min", "5": "5min", "15": "15min", "30": "30min",
    "60": "1h", "240": "4h", "1440": "1day",
}

# Range key → (td_interval, tf_minutes_str, outputsize)
RANGE_CONFIG: Dict[str, Tuple[str, str, int]] = {
    "1h":  ("1min",  "1",    60),
    "4h":  ("1min",  "1",   240),
    "1d":  ("5min",  "5",   288),
    "1w":  ("15min", "15",  672),
    "1m":  ("1h",    "60",  720),
    "3m":  ("4h",    "240", 540),
}

TWELVEDATA_BASE = "https://api.twelvedata.com"


# ── Twelvedata REST API ───────────────────────────────────────────────────────

def _get_api_key() -> str:
    return os.getenv("TWELVEDATA_API_KEY", "").strip()


def _parse_td_dt(dt_str: str) -> datetime:
    try:
        if " " in dt_str:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return datetime.strptime(dt_str, "%Y-%m-%d")
    except ValueError:
        return datetime.utcnow()


def fetch_twelvedata(symbol: str, interval: str, outputsize: int = 200) -> List[Dict[str, Any]]:
    """Fetch OHLCV from Twelvedata REST API. Returns sorted ascending."""
    api_key = _get_api_key()
    if not api_key:
        log.debug("TWELVEDATA_API_KEY not set — skipping REST fetch")
        return []

    td_sym = TD_SYMBOL_MAP.get(symbol.upper(), symbol)
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"{TWELVEDATA_BASE}/time_series",
                params={
                    "symbol": td_sym,
                    "interval": interval,
                    "outputsize": min(outputsize, 5000),
                    "apikey": api_key,
                    "format": "JSON",
                    "timezone": "UTC",
                },
            )
        data = resp.json()
    except Exception as exc:
        log.warning("Twelvedata request failed: %s", exc)
        return []

    if data.get("status") == "error":
        log.warning("Twelvedata API error [%s/%s]: %s", symbol, interval, data.get("message"))
        return []

    result = []
    for v in data.get("values", []):
        try:
            result.append({
                "timestamp": _parse_td_dt(v["datetime"]),
                "open":   float(v["open"]),
                "high":   float(v["high"]),
                "low":    float(v["low"]),
                "close":  float(v["close"]),
                "volume": float(v.get("volume") or 0),
            })
        except (KeyError, ValueError):
            continue

    result.sort(key=lambda x: x["timestamp"])
    log.info("Twelvedata: fetched %d %s candles for %s", len(result), interval, symbol)
    return result


# ── yfinance fallback ─────────────────────────────────────────────────────────

_YF_INTERVAL: Dict[str, str] = {
    "1": "1m", "5": "5m", "15": "15m", "60": "1h",
    "240": "1h", "1440": "1d",
}
_YF_PERIOD: Dict[str, str] = {
    "1": "5d", "5": "30d", "15": "30d", "60": "60d",
    "240": "60d", "1440": "2y",
}


def _fetch_yfinance(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    try:
        import yfinance as yf
        yf_sym = YF_SYMBOL_MAP.get(symbol.upper(), symbol)
        interval = _YF_INTERVAL.get(str(timeframe), "1h")
        period = _YF_PERIOD.get(str(timeframe), "60d")

        df = yf.Ticker(yf_sym).history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return []

        df.index = pd.to_datetime(df.index, utc=True)
        if str(timeframe) == "240":
            df = df.resample("4h").agg(
                {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
            ).dropna()

        result = []
        for ts, row in df.tail(limit).iterrows():
            dt = ts.to_pydatetime()
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            result.append({
                "timestamp": dt,
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            })

        log.info("yfinance: fetched %d candles for %s tf=%s", len(result), symbol, timeframe)
        return result
    except Exception as exc:
        log.warning("yfinance error for %s tf=%s: %s", symbol, timeframe, exc)
        return []


# ── Public fetch API ──────────────────────────────────────────────────────────

def fetch_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch candles: Twelvedata first, yfinance fallback. No synthetic data."""
    interval = TF_TO_TD.get(str(timeframe), "1h")
    candles = fetch_twelvedata(symbol, interval, limit)
    if candles:
        return candles

    log.info("Twelvedata unavailable — trying yfinance for %s tf=%s", symbol, timeframe)
    return _fetch_yfinance(symbol, timeframe, limit)


def fetch_candles_by_range(symbol: str, range_key: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Fetch real candles for a given time range.
    Returns (candles, timeframe_minutes_str).
    """
    cfg = RANGE_CONFIG.get(range_key.lower(), RANGE_CONFIG["1w"])
    td_interval, tf_str, outputsize = cfg

    candles = fetch_twelvedata(symbol, td_interval, outputsize)
    if not candles:
        candles = _fetch_yfinance(symbol, tf_str, outputsize)

    return candles, tf_str


# ── DB helpers ────────────────────────────────────────────────────────────────

def upsert_candles(db, symbol: str, timeframe: str, rows: List[Dict[str, Any]]) -> int:
    from models.candle import Candle
    if not rows:
        return 0
    count = 0
    for row in rows:
        existing = (
            db.query(Candle)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == str(timeframe),
                Candle.timestamp == row["timestamp"],
            )
            .first()
        )
        if existing:
            existing.open  = row["open"]
            existing.high  = row["high"]
            existing.low   = row["low"]
            existing.close = row["close"]
            existing.volume = row["volume"]
        else:
            db.add(Candle(
                symbol=symbol, timeframe=str(timeframe),
                timestamp=row["timestamp"],
                open=row["open"], high=row["high"],
                low=row["low"],  close=row["close"],
                volume=row["volume"],
            ))
            count += 1
    db.commit()
    return count


def fetch_and_store(db, symbol: str, timeframe: str, limit: int = 200) -> List[Any]:
    """Fetch, upsert, return candles from DB."""
    from models.candle import Candle
    rows = fetch_candles(symbol, timeframe, limit)
    if rows:
        upsert_candles(db, symbol, timeframe, rows)

    db_rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(db_rows))


def fetch_and_store_by_range(db, symbol: str, range_key: str) -> Tuple[List[Dict], str]:
    """Fetch fresh real candles by range, upsert them, and return the fetched rows."""
    rows, timeframe = fetch_candles_by_range(symbol, range_key)
    if not rows:
        return [], timeframe

    upsert_candles(db, symbol, timeframe, rows)
    result = [
        {
            "id": 0,
            "timestamp": r["timestamp"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
        }
        for r in rows
    ]
    return result, timeframe


def _candles_as_dicts(rows) -> List[Dict]:
    """Convert SQLAlchemy Candle objects or dicts to plain dicts."""
    result = []
    for r in rows:
        if isinstance(r, dict):
            result.append(r)
        else:
            result.append({
                "id": r.id, "timestamp": r.timestamp,
                "open": r.open, "high": r.high, "low": r.low,
                "close": r.close, "volume": r.volume,
            })
    return result


# ── Latest tick ───────────────────────────────────────────────────────────────

def get_latest_tick(symbol: str) -> Dict[str, Any]:
    """Return current price from Twelvedata WS cache → yfinance. No synthetic."""
    from services.twelvedata_service import get_price as td_price
    cached = td_price(symbol)
    if cached:
        return cached

    try:
        import yfinance as yf
        ticker = yf.Ticker(YF_SYMBOL_MAP.get(symbol.upper(), symbol))
        info = ticker.fast_info
        price = float(getattr(info, "last_price", 0) or 0)
        if price == 0:
            df = ticker.history(period="1d", interval="1m")
            if not df.empty:
                price = float(df["Close"].iloc[-1])
        if price > 0:
            spread = price * 0.0002
            return {
                "symbol": symbol, "price": round(price, 4),
                "bid": round(price - spread / 2, 4),
                "ask": round(price + spread / 2, 4),
                "time": datetime.utcnow().isoformat(),
                "source": "yfinance",
            }
    except Exception:
        pass

    return {
        "symbol": symbol, "price": 0.0, "bid": 0.0, "ask": 0.0,
        "time": datetime.utcnow().isoformat(), "source": "unavailable",
    }


# ── Startup ingest ────────────────────────────────────────────────────────────

def ingest_historical(db, symbol: str = "XAUUSD") -> None:
    """Download real historical candles on startup via Twelvedata."""
    log.info("Starting historical data ingestion for %s via Twelvedata", symbol)
    for tf, interval, outputsize in [
        ("60",   "1h",    720),   # ~1 month of H1
        ("240",  "4h",    540),   # ~3 months of H4
        ("1440", "1day",  730),   # ~2 years of D1
    ]:
        try:
            rows = fetch_twelvedata(symbol, interval, outputsize)
            if not rows:
                log.info("Twelvedata unavailable for tf=%s, trying yfinance", tf)
                rows = _fetch_yfinance(symbol, tf, min(outputsize, 500))
            n = upsert_candles(db, symbol, tf, rows)
            log.info("Ingested %d new candles for %s tf=%s (%d total fetched)", n, symbol, tf, len(rows))
            time.sleep(0.5)
        except Exception:
            log.exception("Historical ingest failed for %s tf=%s", symbol, tf)
