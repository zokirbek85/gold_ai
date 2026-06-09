"""
Data provider chain for OHLCV candles.

Priority (default): Twelvedata → Polygon → yfinance

Each provider is tried in order; the first successful response is returned.
Falls back silently to the next provider if a fetch fails or returns empty data.

Configuration:
    Set DATA_PROVIDERS env var (comma-separated) to override order:
        DATA_PROVIDERS=twelvedata,polygon,yfinance
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger(__name__)

# ── Symbol maps ───────────────────────────────────────────────────────────────

TD_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "XAU/USD", "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY", "BTCUSD": "BTC/USD",
}
YF_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X", "BTCUSD": "BTC-USD",
}
POLYGON_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "C:XAUUSD", "EURUSD": "C:EURUSD", "GBPUSD": "C:GBPUSD",
    "USDJPY": "C:USDJPY", "BTCUSD": "X:BTCUSD",
}

TF_TO_TD: Dict[str, str] = {
    "1": "1min", "5": "5min", "15": "15min", "30": "30min",
    "60": "1h", "240": "4h", "1440": "1day",
}

# Polygon multiplier + timespan for each timeframe (minutes string)
TF_TO_POLYGON: Dict[str, Tuple[int, str]] = {
    "1": (1, "minute"), "5": (5, "minute"), "15": (15, "minute"),
    "30": (30, "minute"), "60": (1, "hour"), "240": (4, "hour"),
    "1440": (1, "day"),
}


# ── Candle dict normaliser ────────────────────────────────────────────────────

def _candle(ts: datetime, o: float, h: float, lo: float, c: float, v: float) -> Dict:
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return {"timestamp": ts, "open": o, "high": h, "low": lo, "close": c, "volume": v}


# ── Provider 1: Twelvedata ────────────────────────────────────────────────────

def _fetch_twelvedata(symbol: str, timeframe: str, limit: int) -> List[Dict]:
    api_key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        return []

    td_sym   = TD_SYMBOL_MAP.get(symbol.upper(), symbol)
    interval = TF_TO_TD.get(str(timeframe), "1h")
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": td_sym, "interval": interval,
                    "outputsize": min(limit, 5000),
                    "apikey": api_key, "format": "JSON", "timezone": "UTC",
                },
            )
        data = resp.json()
    except Exception as exc:
        log.debug("Twelvedata request failed: %s", exc)
        return []

    if data.get("status") == "error":
        log.debug("Twelvedata error [%s/%s]: %s", symbol, interval, data.get("message"))
        return []

    result = []
    for v in data.get("values", []):
        try:
            ts_raw = v["datetime"]
            ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S") if " " in ts_raw \
                 else datetime.strptime(ts_raw, "%Y-%m-%d")
            result.append(_candle(
                ts, float(v["open"]), float(v["high"]),
                float(v["low"]), float(v["close"]),
                float(v.get("volume") or 0),
            ))
        except (KeyError, ValueError):
            continue

    result.sort(key=lambda x: x["timestamp"])
    log.info("Twelvedata: %d candles [%s %s]", len(result), symbol, timeframe)
    return result


# ── Provider 2: Polygon.io ────────────────────────────────────────────────────

def _fetch_polygon(symbol: str, timeframe: str, limit: int) -> List[Dict]:
    api_key = os.getenv("POLYGON_API_KEY", "").strip()
    if not api_key:
        return []

    poly_sym = POLYGON_SYMBOL_MAP.get(symbol.upper(), symbol)
    mult, span = TF_TO_POLYGON.get(str(timeframe), (1, "hour"))
    from datetime import timedelta
    now  = datetime.now(timezone.utc)
    from_dt = (now - timedelta(days=limit // (24 * 60 // int(timeframe) or 1) + 1)).strftime("%Y-%m-%d")
    to_dt   = now.strftime("%Y-%m-%d")

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{poly_sym}/range/{mult}/{span}/{from_dt}/{to_dt}",
                params={"adjusted": "true", "sort": "asc", "limit": limit, "apiKey": api_key},
            )
        data = resp.json()
    except Exception as exc:
        log.debug("Polygon request failed: %s", exc)
        return []

    if data.get("status") not in ("OK", "DELAYED"):
        log.debug("Polygon error [%s]: %s", symbol, data.get("message"))
        return []

    result = []
    for bar in data.get("results", []):
        try:
            ts = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc)
            result.append(_candle(ts, bar["o"], bar["h"], bar["l"], bar["c"], bar.get("v", 0)))
        except (KeyError, ValueError):
            continue

    log.info("Polygon: %d candles [%s %s]", len(result), symbol, timeframe)
    return result


# ── Provider 3: yfinance ──────────────────────────────────────────────────────

_YF_INTERVAL: Dict[str, str] = {
    "1": "1m", "5": "5m", "15": "15m", "60": "1h",
    "240": "1h", "1440": "1d",
}
_YF_PERIOD: Dict[str, str] = {
    "1": "5d", "5": "30d", "15": "30d",
    "60": "60d", "240": "60d", "1440": "2y",
}


def _fetch_yfinance(symbol: str, timeframe: str, limit: int) -> List[Dict]:
    try:
        import yfinance as yf
        import pandas as pd
        yf_sym   = YF_SYMBOL_MAP.get(symbol.upper(), symbol)
        interval = _YF_INTERVAL.get(str(timeframe), "1h")
        period   = _YF_PERIOD.get(str(timeframe), "60d")

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
            result.append(_candle(
                ts.to_pydatetime(),
                float(row["Open"]), float(row["High"]), float(row["Low"]),
                float(row["Close"]), float(row.get("Volume", 0) or 0),
            ))
        log.info("yfinance: %d candles [%s %s]", len(result), symbol, timeframe)
        return result
    except Exception as exc:
        log.debug("yfinance error [%s %s]: %s", symbol, timeframe, exc)
        return []


# ── Provider chain ────────────────────────────────────────────────────────────

_PROVIDERS = {
    "twelvedata": _fetch_twelvedata,
    "polygon":    _fetch_polygon,
    "yfinance":   _fetch_yfinance,
}


def fetch_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
    providers: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Fetch OHLCV candles using the provider chain.
    Falls through to the next provider if the current one returns empty data.
    """
    if providers is None:
        env_chain = os.getenv("DATA_PROVIDERS", "twelvedata,polygon,yfinance")
        providers = [p.strip() for p in env_chain.split(",") if p.strip()]

    for name in providers:
        fn = _PROVIDERS.get(name)
        if not fn:
            log.debug("Unknown provider '%s' — skipping", name)
            continue
        try:
            candles = fn(symbol, timeframe, limit)
            if candles:
                return candles
            log.info("Provider '%s' returned no data for %s %s — trying next", name, symbol, timeframe)
        except Exception as exc:
            log.warning("Provider '%s' raised exception for %s %s: %s", name, symbol, timeframe, exc)

    log.warning("All providers exhausted for %s %s", symbol, timeframe)
    return []
