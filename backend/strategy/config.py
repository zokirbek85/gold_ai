"""
Strategy and risk parameters.

Every value here is a default, not a validated "optimal" setting. Values can be
overridden with environment variables prefixed ``GOLDAI_`` (e.g.
``GOLDAI_TARGET_RR=2.5``). Broker-specific values (spread, contract size, lot
step) MUST be checked against the user's broker before trusting position
sizes — the defaults are generic XAUUSD retail assumptions.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, fields


def _env_override(obj) -> None:
    for f in fields(obj):
        raw = os.getenv(f"GOLDAI_{f.name.upper()}")
        if raw is None or raw == "":
            continue
        try:
            if f.type in (bool, "bool"):
                setattr(obj, f.name, raw.strip().lower() in ("1", "true", "yes"))
            elif f.type in (int, "int"):
                setattr(obj, f.name, int(raw))
            elif f.type in (float, "float"):
                setattr(obj, f.name, float(raw))
            else:
                setattr(obj, f.name, raw)
        except ValueError:
            pass  # keep default on malformed input


@dataclass
class StrategyConfig:
    # ── Timeframes (minutes) ────────────────────────────────────────────────
    # H4/D1 chosen on the 2021-01…2024-06 train period (see docs/GOLD_AI_AUDIT_2026-10.md);
    # the same rules on H1/H4 showed no out-of-sample edge.
    primary_tf: int = 240         # setup + trigger timeframe
    context_tf: int = 1440        # higher-timeframe trend context

    # ── Indicator periods ───────────────────────────────────────────────────
    ema_fast: int = 20
    ema_slow: int = 50
    ema_trend: int = 200
    atr_period: int = 14
    adx_period: int = 14
    rsi_period: int = 14
    atr_baseline: int = 100       # bars for median-ATR volatility baseline

    # ── Regime thresholds ───────────────────────────────────────────────────
    adx_trend_min: float = 22.0
    adx_range_max: float = 18.0
    vol_high_ratio: float = 2.0   # ATR / median ATR above → HIGH_VOLATILITY
    vol_low_ratio: float = 0.5    # below → LOW_VOLATILITY

    # ── Setup rules ─────────────────────────────────────────────────────────
    # "strict": H4 trend must agree; "not_against": H4 must not oppose
    context_mode: str = "strict"
    pullback_lookback: int = 5        # bars in which the pullback must occur
    pullback_touch_atr: float = 0.25  # low within this many ATR of EMA_fast
    rsi_buy_max: float = 70.0         # don't buy into overbought
    rsi_sell_min: float = 30.0        # don't sell into oversold
    enable_range_setup: bool = False  # mean-reversion setup (off until validated)
    range_rsi_buy: float = 35.0
    range_rsi_sell: float = 65.0

    # ── SL / TP ─────────────────────────────────────────────────────────────
    sl_swing_lookback: int = 5
    sl_buffer_atr: float = 0.2
    sl_min_atr: float = 0.8
    sl_max_atr: float = 2.5
    target_rr: float = 2.5
    tp1_rr: float = 1.0               # informational partial-profit level
    min_rr: float = 1.5               # after costs
    min_room_r: float = 0.0           # 0 = off (the 1R room filter hurt in train)
    room_swing_lookback: int = 50

    # ── Signal lifetime ─────────────────────────────────────────────────────
    expiry_bars: int = 2              # entry must happen within N primary bars
    entry_zone_atr: float = 0.3       # max chase distance from reference entry
    max_hold_bars: int = 48           # backtest time-exit

    # ── Session / data ──────────────────────────────────────────────────────
    rollover_start_utc: int = 21      # no new signals 21:00–23:00 UTC (spreads widen)
    rollover_end_utc: int = 23
    min_history_bars: int = 250
    max_stale_bars: float = 1.5       # last closed bar older than this → stale
    max_gap_bars_in_window: int = 3   # unexplained gaps (non-weekend) tolerated
    news_blackout_minutes: int = 30

    # ── Scoring ─────────────────────────────────────────────────────────────
    min_signal_score: float = 0.0     # 0 = score is informational only

    def __post_init__(self) -> None:
        _env_override(self)

    def version_hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


@dataclass
class RiskConfig:
    # Costs in price units (USD per oz). Defaults are assumptions — set from broker.
    spread: float = 0.30
    slippage: float = 0.10            # per fill
    commission_per_lot: float = 0.0   # round-turn, account currency
    # Overnight financing in USD/oz per night held through 21:00 UTC (negative = cost).
    # Broker-specific and usually negative for gold longs — 0 means "unknown", not "free".
    swap_long: float = 0.0
    swap_short: float = 0.0
    max_spread: float = 0.60
    max_spread_to_risk: float = 0.15  # spread must be < 15 % of SL distance

    # Position sizing — verify with broker symbol specification
    risk_pct: float = 0.5             # % of balance per trade (conservative default)
    contract_size: float = 100.0      # oz per 1.0 lot
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 5.0

    def __post_init__(self) -> None:
        _env_override(self)
