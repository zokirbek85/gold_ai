"""
Twelvedata WebSocket real-time price feed.

Free tier at https://twelvedata.com — sign up, copy API key, set env var:
  TWELVEDATA_API_KEY=your_key_here

Supported symbols: XAU/USD, EUR/USD, GBP/USD, BTC/USD, etc.
WebSocket endpoint: wss://ws.twelvedata.com/v1/quotes/price
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

log = logging.getLogger(__name__)

# In-memory price cache: symbol (e.g. "XAUUSD") -> price dict
_prices: Dict[str, dict] = {}
_lock = threading.Lock()

# Map our internal symbols to Twelvedata symbols
_SYMBOL_MAP = {
    "XAUUSD": "XAU/USD",
    "EURUSD": "EUR/USD",
    "BTCUSD": "BTC/USD",
}

_ws_instance = None
_running = False


def _normalize(td_symbol: str) -> str:
    """XAU/USD → XAUUSD"""
    return td_symbol.replace("/", "").replace("-", "").upper()


def get_price(symbol: str) -> Optional[dict]:
    """Return cached real-time price or None if not available."""
    with _lock:
        return _prices.get(symbol.upper())


def is_connected() -> bool:
    return _running


# ── WebSocket client ──────────────────────────────────────────────────────────

def _run_ws(api_key: str):
    global _running, _ws_instance
    try:
        import websocket
    except ImportError:
        log.error("websocket-client not installed. Run: pip install websocket-client")
        return

    symbols_str = ",".join(_SYMBOL_MAP.values())

    def on_open(ws):
        global _running
        _running = True
        payload = json.dumps({
            "action": "subscribe",
            "params": {"symbols": symbols_str},
        })
        ws.send(payload)
        log.info("Twelvedata WS connected — subscribed to: %s", symbols_str)

    def on_message(ws, raw):
        try:
            d = json.loads(raw)
            event = d.get("event")

            if event == "price":
                td_sym = d.get("symbol", "")
                price = float(d.get("price", 0) or 0)
                if price <= 0:
                    return

                our_sym = _normalize(td_sym)
                spread = price * 0.0002
                ts = d.get("timestamp", "")
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                entry = {
                    "symbol": our_sym,
                    "price": round(price, 4),
                    "bid": round(price - spread / 2, 4),
                    "ask": round(price + spread / 2, 4),
                    "time": ts,
                    "source": "twelvedata",
                }
                with _lock:
                    _prices[our_sym] = entry
                log.debug("TD price: %s = %.4f", our_sym, price)

            elif event == "subscribe-status":
                log.info("Twelvedata subscribe status: %s", d)

            elif event == "heartbeat":
                pass

        except Exception as exc:
            log.warning("Twelvedata on_message error: %s", exc)

    def on_error(ws, error):
        log.error("Twelvedata WS error: %s", error)

    def on_close(ws, code, msg):
        global _running
        _running = False
        log.warning("Twelvedata WS closed (%s %s) — reconnecting in 15s", code, msg)
        time.sleep(15)
        _run_ws(api_key)  # reconnect

    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={api_key}"
    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    _ws_instance = ws
    ws.run_forever(ping_interval=30, ping_timeout=10)


def start(api_key: Optional[str] = None) -> bool:
    """
    Start the Twelvedata WebSocket in a background daemon thread.
    Returns True if started, False if no API key.
    """
    key = api_key or os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not key:
        log.info(
            "TWELVEDATA_API_KEY not set — real-time feed disabled. "
            "Get a free key at https://twelvedata.com and set TWELVEDATA_API_KEY."
        )
        return False

    t = threading.Thread(target=_run_ws, args=(key,), daemon=True, name="twelvedata-ws")
    t.start()
    log.info("Twelvedata WebSocket thread started")
    return True
