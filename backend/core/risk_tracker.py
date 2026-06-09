"""
DailyRiskTracker — Redis-backed per-account risk guardrails.

Tracks:
- Daily realised P&L (loss floor)
- Weekly realised P&L (loss floor)
- Count of currently open trades
- Count of correlated-pair trades

All keys expire at UTC midnight so counters reset automatically.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Defaults — overridable per account
MAX_DAILY_LOSS_PCT: float = 0.03    # 3% of account
MAX_WEEKLY_LOSS_PCT: float = 0.06   # 6% of account
MAX_OPEN_TRADES: int = 5
MAX_CORRELATED_TRADES: int = 2      # e.g. XAUUSD + XAGUSD at same time


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight - now).total_seconds())


def _seconds_until_next_monday() -> int:
    now = datetime.now(timezone.utc)
    days_ahead = 7 - now.weekday()
    next_monday = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((next_monday - now).total_seconds())


class DailyRiskTracker:
    """
    Thread-safe, Redis-backed daily/weekly risk tracker.
    Degrades gracefully (passes all checks) when Redis is unavailable.
    """

    def __init__(self, redis_client=None) -> None:
        self._r = redis_client

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _key(self, account_id: str, suffix: str) -> str:
        return f"risk:{account_id}:{suffix}"

    def _get_float(self, key: str) -> float:
        if not self._r:
            return 0.0
        try:
            v = self._r.get(key)
            return float(v) if v else 0.0
        except Exception:
            return 0.0

    def _get_int(self, key: str) -> int:
        if not self._r:
            return 0
        try:
            v = self._r.get(key)
            return int(v) if v else 0
        except Exception:
            return 0

    def _incr_float(self, key: str, delta: float, ttl: int) -> None:
        if not self._r:
            return
        try:
            pipe = self._r.pipeline()
            pipe.incrbyfloat(key, delta)
            pipe.expire(key, ttl)
            pipe.execute()
        except Exception as exc:
            log.debug("risk_tracker incr_float error: %s", exc)

    def _set_int(self, key: str, value: int, ttl: int) -> None:
        if not self._r:
            return
        try:
            self._r.setex(key, ttl, value)
        except Exception as exc:
            log.debug("risk_tracker set_int error: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def record_trade_pnl(self, account_id: str, pnl_usd: float) -> None:
        """Call when a trade closes. pnl_usd is positive=profit, negative=loss."""
        ttl_day = _seconds_until_utc_midnight()
        ttl_week = _seconds_until_next_monday()
        self._incr_float(self._key(account_id, "daily_pnl"), pnl_usd, ttl_day)
        self._incr_float(self._key(account_id, "weekly_pnl"), pnl_usd, ttl_week)

    def record_trade_opened(self, account_id: str, symbol: str) -> None:
        """Call when a new trade is opened."""
        ttl_day = _seconds_until_utc_midnight()
        open_key = self._key(account_id, "open_trades")
        corr_key = self._key(account_id, f"corr:{_corr_group(symbol)}")
        if not self._r:
            return
        try:
            pipe = self._r.pipeline()
            pipe.incr(open_key);  pipe.expire(open_key, ttl_day)
            pipe.incr(corr_key);  pipe.expire(corr_key, ttl_day)
            pipe.execute()
        except Exception as exc:
            log.debug("risk_tracker record_opened error: %s", exc)

    def record_trade_closed(self, account_id: str, symbol: str) -> None:
        """Call when a trade is closed (decrement open count)."""
        open_key = self._key(account_id, "open_trades")
        corr_key = self._key(account_id, f"corr:{_corr_group(symbol)}")
        if not self._r:
            return
        try:
            self._r.decr(open_key)
            self._r.decr(corr_key)
        except Exception:
            pass

    def can_trade(
        self,
        account_id: str,
        account_balance: float,
        symbol: str,
        max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT,
        max_weekly_loss_pct: float = MAX_WEEKLY_LOSS_PCT,
        max_open_trades: int = MAX_OPEN_TRADES,
        max_correlated: int = MAX_CORRELATED_TRADES,
    ) -> Dict[str, Any]:
        """
        Returns: {"allowed": bool, "reasons": List[str], "stats": dict}
        Passes (allowed=True) when Redis is unavailable.
        """
        reasons: list[str] = []
        daily_pnl  = self._get_float(self._key(account_id, "daily_pnl"))
        weekly_pnl = self._get_float(self._key(account_id, "weekly_pnl"))
        open_count = self._get_int(self._key(account_id, "open_trades"))
        corr_count = self._get_int(self._key(account_id, f"corr:{_corr_group(symbol)}"))

        daily_loss_floor  = -account_balance * max_daily_loss_pct
        weekly_loss_floor = -account_balance * max_weekly_loss_pct

        if daily_pnl < daily_loss_floor:
            reasons.append(
                f"Daily loss limit hit: ${daily_pnl:.2f} < ${daily_loss_floor:.2f}"
            )
        if weekly_pnl < weekly_loss_floor:
            reasons.append(
                f"Weekly loss limit hit: ${weekly_pnl:.2f} < ${weekly_loss_floor:.2f}"
            )
        if open_count >= max_open_trades:
            reasons.append(f"Max open trades reached: {open_count}/{max_open_trades}")
        if corr_count >= max_correlated:
            reasons.append(
                f"Max correlated trades reached: {corr_count}/{max_correlated} for {_corr_group(symbol)}"
            )

        return {
            "allowed": len(reasons) == 0,
            "reasons": reasons,
            "stats": {
                "daily_pnl":   round(daily_pnl, 2),
                "weekly_pnl":  round(weekly_pnl, 2),
                "open_trades": open_count,
                "corr_trades": corr_count,
            },
        }

    def status(self, account_id: str, account_balance: float) -> Dict[str, Any]:
        """Return full risk status for the account."""
        daily_pnl  = self._get_float(self._key(account_id, "daily_pnl"))
        weekly_pnl = self._get_float(self._key(account_id, "weekly_pnl"))
        open_count = self._get_int(self._key(account_id, "open_trades"))
        return {
            "account_id":      account_id,
            "account_balance": account_balance,
            "daily_pnl":       round(daily_pnl, 2),
            "daily_pnl_pct":   round(daily_pnl / account_balance * 100, 2) if account_balance else 0,
            "weekly_pnl":      round(weekly_pnl, 2),
            "weekly_pnl_pct":  round(weekly_pnl / account_balance * 100, 2) if account_balance else 0,
            "open_trades":     open_count,
            "max_daily_loss_pct":  MAX_DAILY_LOSS_PCT * 100,
            "max_weekly_loss_pct": MAX_WEEKLY_LOSS_PCT * 100,
            "max_open_trades": MAX_OPEN_TRADES,
        }


def _corr_group(symbol: str) -> str:
    """Map symbol to its correlation group for diversification checks."""
    gold_group = {"XAUUSD", "XAGUSD", "GC", "SI"}
    usd_group  = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}
    jpy_group  = {"USDJPY", "EURJPY", "GBPJPY"}
    s = symbol.upper()
    if s in gold_group:
        return "metals"
    if s in usd_group:
        return "usd_majors"
    if s in jpy_group:
        return "jpy"
    return s


# Module-level singleton — wired to Redis at startup
_daily_risk_tracker: Optional[DailyRiskTracker] = None


def get_risk_tracker() -> DailyRiskTracker:
    global _daily_risk_tracker
    if _daily_risk_tracker is None:
        try:
            import redis as _redis_mod
            from config import settings
            r = _redis_mod.Redis.from_url(
                settings.REDIS_URL, decode_responses=True,
                socket_connect_timeout=2, socket_timeout=2,
            )
            r.ping()
            _daily_risk_tracker = DailyRiskTracker(r)
            log.info("DailyRiskTracker: Redis connected")
        except Exception as exc:
            log.warning("DailyRiskTracker: Redis unavailable (%s) — risk checks disabled", exc)
            _daily_risk_tracker = DailyRiskTracker(None)
    return _daily_risk_tracker
