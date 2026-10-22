"""
Execution modes and the live-trading readiness gate.

    SIGNAL_ONLY  signals + Telegram, no positions           (implemented)
    PAPER        virtual positions in paper_trades           (implemented)
    DEMO_BROKER  broker demo account via a BrokerAdapter     (NOT implemented)
    LIVE         real account                                (NOT implemented, blocked)

Real orders are impossible in this codebase: no BrokerAdapter implementation
exists and ``assert_live_allowed`` raises unless EVERY readiness check passes,
one of which is "a broker adapter is implemented and verified". Enabling live
trading would require code changes, a reviewed adapter, and the explicit
consent file — a single env flag can never do it.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Protocol

SIGNAL_ONLY, PAPER, DEMO_BROKER, LIVE = "signal_only", "paper", "demo_broker", "live"
IMPLEMENTED_MODES = {SIGNAL_ONLY, PAPER}

# Readiness thresholds (documented in docs/GOLD_AI_LAB_2026-10.md)
MIN_PAPER_TRADES = 100
MIN_PAPER_DAYS = 180


class LiveTradingBlocked(RuntimeError):
    pass


class BrokerAdapter(Protocol):  # interface for a future, reviewed implementation
    account_id: str
    is_demo: bool

    def account_info(self) -> Dict[str, Any]: ...
    def symbol_spec(self, symbol: str) -> Dict[str, Any]: ...      # contract size, lot step, min lot
    def quote(self, symbol: str) -> Dict[str, float]: ...           # real bid/ask
    def place_order(self, order: Dict[str, Any], client_id: str) -> Dict[str, Any]: ...  # idempotent by client_id
    def order_status(self, client_id: str) -> Dict[str, Any]: ...
    def open_positions(self) -> List[Dict[str, Any]]: ...
    def close_all(self) -> None: ...                                # emergency stop


BROKER_ADAPTERS: Dict[str, type] = {}  # intentionally empty


def current_mode() -> str:
    mode = (os.getenv("TRADING_MODE") or SIGNAL_ONLY).lower()
    if mode not in IMPLEMENTED_MODES:
        # never escalate on a typo or an unimplemented mode — fall back to the safest mode
        return SIGNAL_ONLY
    return mode


def _risk_fingerprint() -> str:
    from strategy.config import RiskConfig
    return hashlib.sha256(json.dumps(asdict(RiskConfig()), sort_keys=True).encode()).hexdigest()[:12]


def readiness(paper_stats: Optional[Dict[str, Any]] = None, health: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ps, hs = paper_stats or {}, health or {}
    ci = ps.get("expectancy_r_ci95") or [None, None]
    consent_path = os.getenv("LIVE_TRADING_CONSENT_FILE", "")
    consent_ok = False
    if consent_path and os.path.exists(consent_path):
        try:
            with open(consent_path) as f:
                c = json.load(f)
            consent_ok = bool(c.get("account_id")) and c.get("risk_fingerprint") == _risk_fingerprint()
        except (OSError, ValueError):
            consent_ok = False
    checks = [
        ("broker_adapter_implemented", bool(BROKER_ADAPTERS), "Broker adapteri yozilmagan va tekshirilmagan"),
        ("paper_trades", (ps.get("trades") or 0) >= MIN_PAPER_TRADES, f"≥{MIN_PAPER_TRADES} yopilgan paper savdo kerak (bor: {ps.get('trades', 0)})"),
        ("paper_days", (ps.get("days") or 0) >= MIN_PAPER_DAYS, f"≥{MIN_PAPER_DAYS} kunlik paper tarix kerak (bor: {ps.get('days', 0)})"),
        ("paper_expectancy_ci", ci[0] is not None and ci[0] > 0, f"Paper expectancy CI95 pastki chegarasi > 0 bo'lishi kerak (bor: {ci[0]})"),
        ("strategy_health", hs.get("status") == "OK", f"Strategiya holati OK bo'lishi kerak (bor: {hs.get('status')})"),
        ("explicit_consent", consent_ok, "Imzolangan rozilik fayli (account_id + joriy risk konfiguratsiyasi xeshi) yo'q"),
        ("risk_limits", True, "Risk limitlari: per-trade %, kunlik/umumiy DD, max pozitsiya — RiskConfig/paper limitlarida"),
    ]
    items = [{"check": k, "passed": bool(p), "detail": d} for k, p, d in checks]
    return {"mode": current_mode(), "live_allowed": all(i["passed"] for i in items),
            "checks": items, "risk_fingerprint": _risk_fingerprint()}


def assert_live_allowed(paper_stats=None, health=None) -> None:
    r = readiness(paper_stats, health)
    if not r["live_allowed"]:
        failed = [i["check"] for i in r["checks"] if not i["passed"]]
        raise LiveTradingBlocked(f"Live trading blocked: {failed}")
