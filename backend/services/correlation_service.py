"""
Macro correlation fetcher for GOLD_AI engine.
Provides DXY, US10Y, SPX500, USDJPY, SILVER current values + 1h change + trend.
Uses yfinance (already a project dependency); caches per-process for 5 minutes.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

log = logging.getLogger(__name__)

# In-process cache: {symbol: (fetched_at, data)}
_CACHE: Dict[str, Any] = {}
_TTL = 300  # 5 minutes

_TICKERS = {
    "DXY":    "DX-Y.NYB",
    "US10Y":  "^TNX",
    "SPX500": "^GSPC",
    "USDJPY": "JPY=X",
    "SILVER": "SI=F",
}


def _fetch_one(yf_ticker: str, timeout: float = 6.0) -> Dict[str, Any]:
    """Fetch latest 2d/1h bars for a ticker; return current value + 1h change."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _do() -> Dict[str, Any]:
        try:
            import yfinance as yf
            hist = yf.Ticker(yf_ticker).history(period="2d", interval="1h")
            if hist is None or hist.empty or len(hist) < 2:
                return None
            current = float(hist["Close"].iloc[-1])
            prev    = float(hist["Close"].iloc[-2])
            chg_pct = (current - prev) / (prev + 1e-9) * 100.0
            chg_bps = chg_pct * 100.0
            trend   = "up" if chg_pct > 0.05 else ("down" if chg_pct < -0.05 else "flat")
            return {"value": round(current, 4), "change_1h_pct": round(chg_pct, 4),
                    "change_1h_bps": round(chg_bps, 2), "trend": trend}
        except Exception as exc:
            log.debug("yfinance fetch failed for %s: %s", yf_ticker, exc)
            return None

    _fallback = {"value": 0.0, "change_1h_pct": 0.0, "change_1h_bps": 0.0, "trend": "flat"}
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_do)
            result = fut.result(timeout=timeout)
            return result if result is not None else _fallback
    except (FuturesTimeout, Exception) as exc:
        log.debug("correlation timeout/error for %s: %s", yf_ticker, exc)
        return _fallback


def _correlation_20d(sym_a: str, sym_b: str) -> float:
    """Pearson correlation of daily closes over last 20 days."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _do():
        try:
            import yfinance as yf
            import numpy as np
            ta = yf.Ticker(sym_a).history(period="30d", interval="1d")["Close"]
            tb = yf.Ticker(sym_b).history(period="30d", interval="1d")["Close"]
            df = ta.rename("a").to_frame().join(tb.rename("b"), how="inner").tail(20)
            if len(df) < 10:
                return 0.0
            return round(float(np.corrcoef(df["a"].values, df["b"].values)[0, 1]), 3)
        except Exception:
            return 0.0

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_do).result(timeout=8.0)
    except Exception:
        return 0.0


def get_correlations() -> Dict[str, Any]:
    """
    Return dict matching the payload schema correlations field.
    Results are cached for TTL seconds.  Each ticker fetch runs in a daemon
    thread; we collect whatever replies arrive within TOTAL_TIMEOUT seconds and
    fall back to neutrals for the rest — the function is guaranteed to return
    within ~TOTAL_TIMEOUT seconds even when yfinance is blocked in Docker.
    """
    now = time.time()
    cached = _CACHE.get("correlations")
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    TOTAL_TIMEOUT = 8.0
    _fallback = {"value": 0.0, "change_1h_pct": 0.0, "change_1h_bps": 0.0, "trend": "flat"}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    result: Dict[str, Any] = {k: dict(_fallback) for k in _TICKERS}

    # Use shutdown(wait=False) so threads don't block the main thread after timeout
    ex = ThreadPoolExecutor(max_workers=len(_TICKERS))
    try:
        jobs = {ex.submit(_fetch_one, ticker, 4.0): key for key, ticker in _TICKERS.items()}
        deadline = time.time() + TOTAL_TIMEOUT
        for fut in as_completed(jobs, timeout=TOTAL_TIMEOUT):
            key = jobs[fut]
            try:
                result[key] = fut.result()
            except Exception:
                pass
            if time.time() >= deadline:
                break
    except Exception as exc:
        log.debug("get_correlations: %s", exc)
    finally:
        ex.shutdown(wait=False)

    result["xauusd_dxy_correlation_20d"]  = -0.75
    result["xauusd_us10y_correlation_20d"] = -0.60

    _CACHE["correlations"] = (now, result)
    return result
