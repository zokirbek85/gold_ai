"""
MT4 Connector via ZeroMQ Bridge.

Architecture:
  MT4 EA (Expert Advisor) ←→ ZeroMQ sockets ←→ This connector

Two sockets:
  CMD_PORT  (REQ/REP) — Python sends commands, EA responds with data
  DATA_PORT (PUB/SUB) — EA publishes live ticks/candles, Python subscribes

Compatible with the DWX ZeroMQ Connector EA and similar bridge EAs.
See MT4_CONNECTION_GUIDE.md for full setup instructions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config.settings import settings

log = logging.getLogger(__name__)

try:
    import zmq
    _ZMQ_AVAILABLE = True
except ImportError:
    zmq = None  # type: ignore
    _ZMQ_AVAILABLE = False


class MT4Connector:
    """
    Communicates with a ZeroMQ-enabled MT4 Expert Advisor.

    Command protocol (REQ → EA PULL, EA PUSH → REP):
      Request : JSON string  {"action": "...", "symbol": "XAUUSD", ...}
      Response: JSON string  {"status": "OK", "data": [...]}

    Live data protocol (EA PUB → Python SUB):
      Message : JSON string  {"type": "tick"|"candle", "symbol": "...", ...}
    """

    def __init__(self) -> None:
        self.connected = False
        self._context: Any = None
        self._cmd_socket: Any = None
        self._data_socket: Any = None

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> bool:
        if not _ZMQ_AVAILABLE:
            log.warning("pyzmq not installed — MT4 connector unavailable. Run: pip install pyzmq")
            return False

        host = settings.MT4_HOST or "localhost"
        cmd_port = settings.MT4_CMD_PORT or 32768
        data_port = settings.MT4_DATA_PORT or 32769

        try:
            self._context = zmq.Context()

            # Command socket — send requests to EA, receive responses
            self._cmd_socket = self._context.socket(zmq.REQ)
            self._cmd_socket.setsockopt(zmq.RCVTIMEO, 5000)   # 5s timeout
            self._cmd_socket.setsockopt(zmq.SNDTIMEO, 5000)
            self._cmd_socket.connect(f"tcp://{host}:{cmd_port}")

            # Data socket — subscribe to live market data from EA
            self._data_socket = self._context.socket(zmq.SUB)
            self._data_socket.setsockopt(zmq.RCVTIMEO, 1000)
            self._data_socket.setsockopt_string(zmq.SUBSCRIBE, "")
            self._data_socket.connect(f"tcp://{host}:{data_port}")

            # Test connection with a ping
            response = self._send_command({"action": "PING"})
            if response and response.get("status") == "OK":
                self.connected = True
                log.info("MT4 connector connected — host=%s cmd=%s data=%s", host, cmd_port, data_port)
                return True
            else:
                log.warning("MT4 ping failed — EA may not be running. Response: %s", response)
                self.connected = False
                return False

        except Exception:
            log.exception("MT4 connector failed to connect")
            self.connected = False
            return False

    def shutdown(self) -> None:
        for sock in (self._cmd_socket, self._data_socket):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        if self._context:
            try:
                self._context.term()
            except Exception:
                pass
        self._cmd_socket = None
        self._data_socket = None
        self._context = None
        self.connected = False
        log.info("MT4 connector shut down")

    # ------------------------------------------------------------------ internal
    def _send_command(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._cmd_socket:
            return None
        try:
            self._cmd_socket.send_string(json.dumps(payload))
            raw = self._cmd_socket.recv_string()
            return json.loads(raw)
        except Exception as exc:
            log.warning("MT4 command failed (%s): %s", payload.get("action"), exc)
            self.connected = False
            return None

    # ------------------------------------------------------------------ data API
    def get_ticks(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent ticks from MT4 EA via REQ/REP."""
        if not self.connected:
            return []
        response = self._send_command({"action": "GET_TICKS", "symbol": symbol, "count": n})
        if not response or response.get("status") != "OK":
            return []
        return response.get("data", [])

    def get_candles(self, symbol: str, timeframe: int, count: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV candles from MT4 EA.
        timeframe: minutes (1, 5, 15, 30, 60, 240, 1440)
        """
        if not self.connected:
            return []
        response = self._send_command({
            "action": "GET_CANDLES",
            "symbol": symbol,
            "timeframe": timeframe,
            "count": count,
        })
        if not response or response.get("status") != "OK":
            return []
        return response.get("data", [])

    def get_live_tick(self) -> Optional[Dict[str, Any]]:
        """
        Non-blocking read from the PUB/SUB data socket.
        Returns the latest tick dict if one is available, else None.
        """
        if not self._data_socket:
            return None
        try:
            raw = self._data_socket.recv_string(flags=zmq.NOBLOCK)
            return json.loads(raw)
        except Exception:
            return None

    def get_account_info(self) -> Dict[str, Any]:
        """Fetch MT4 account balance, equity, margin."""
        if not self.connected:
            return {}
        response = self._send_command({"action": "GET_ACCOUNT"})
        return response.get("data", {}) if response else {}


mt4_connector = MT4Connector()
