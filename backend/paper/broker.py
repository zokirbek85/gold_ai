"""
Pure paper-broker logic (no DB). Uses the same fill/exit rules as the backtester
(strategy.backtest.fill_price / step_exit) so paper and backtest results are
comparable:

  PENDING → first CLOSED bar that opens after the signal bar closed:
            open inside the entry zone (and not beyond SL/TP) → fill at that open
            otherwise → CANCELLED (ENTRY_ZONE_MISSED / OPENED_BEYOND_LEVELS)
            no bar before expires_at → CANCELLED (EXPIRED)
  OPEN    → bar by bar: gap through SL, SL (first if both touched), TP,
            time exit after max_hold
Bars must be closed and strictly newer than ``last_bar``; a jump larger than
``max_gap`` between consecutive bars marks ``data_gap`` (path unknown → audit).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from strategy.backtest import _nights, fill_price, step_exit
from strategy.config import RiskConfig

import pandas as pd


@dataclass
class Position:
    direction: str
    status: str
    signal_time: datetime          # close time of the signal bar
    expires_at: datetime
    entry_ref: float
    zone_low: float
    zone_high: float
    stop_loss: float
    take_profit: float
    risk_per_oz: float
    lots: float
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    r_multiple: Optional[float] = None
    pnl_usd: Optional[float] = None
    costs_usd: Optional[float] = None
    mfe_r: float = 0.0
    mae_r: float = 0.0
    bars_processed: int = 0
    last_bar: Optional[datetime] = None
    data_gap: bool = False
    open_minutes: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def side(self) -> int:
        return 1 if self.direction == "BUY" else -1


def process(pos: Position, bars: Iterable[Dict[str, Any]], rc: RiskConfig, bar_minutes: int,
            max_hold: timedelta, max_gap: timedelta = timedelta(minutes=30)) -> Position:
    half, slip, side = rc.spread / 2.0, rc.slippage, pos.side
    for b in bars:
        t = pd.Timestamp(b["timestamp"]).to_pydatetime()
        if pos.status in ("CLOSED", "CANCELLED"):
            break
        if pos.last_bar is not None and t <= pos.last_bar:
            continue
        if t < pos.signal_time:
            continue
        if pos.last_bar is not None and t - pos.last_bar > max_gap:
            # weekend closure is expected; anything else means the path is unknown
            if not (pos.last_bar.weekday() == 4 and t.weekday() in (6, 0)):
                pos.data_gap = True
        o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
        pos.last_bar = t
        pos.bars_processed += 1

        if pos.status == "PENDING":
            if t >= pos.expires_at:
                pos.status, pos.exit_reason = "CANCELLED", "EXPIRED"
                break
            if not (pos.zone_low <= o <= pos.zone_high):
                pos.status, pos.exit_reason = "CANCELLED", "ENTRY_ZONE_MISSED"
                break
            if (side == 1 and (o <= pos.stop_loss or o >= pos.take_profit)) or \
               (side == -1 and (o >= pos.stop_loss or o <= pos.take_profit)):
                pos.status, pos.exit_reason = "CANCELLED", "OPENED_BEYOND_LEVELS"
                break
            pos.fill_price, pos.fill_time, pos.status = fill_price(side, o, half, slip), t, "OPEN"
            gap_check = False
        else:
            gap_check = True

        fav = (h - pos.fill_price) if side == 1 else (pos.fill_price - l)
        adv = (pos.fill_price - l) if side == 1 else (h - pos.fill_price)
        pos.mfe_r = max(pos.mfe_r, fav / pos.risk_per_oz)
        pos.mae_r = max(pos.mae_r, adv / pos.risk_per_oz)

        px, reason = step_exit(side, o, h, l, pos.stop_loss, pos.take_profit, half, slip, gap_check)
        bar_close = t + timedelta(minutes=bar_minutes)
        # holding time counted in TRADING bars (weekends excluded), as in the backtest
        pos.open_minutes += bar_minutes
        if px is None and pos.open_minutes >= max_hold.total_seconds() / 60:
            px, reason = c - side * half, "TIME"
        if px is not None:
            _close(pos, px, reason, bar_close, rc)
    return pos


def _close(pos: Position, px: float, reason: str, when: datetime, rc: RiskConfig) -> None:
    side = pos.side
    comm_per_oz = rc.commission_per_lot / rc.contract_size
    nights = _nights(pd.Timestamp(pos.fill_time), pd.Timestamp(when))
    swap = nights * (rc.swap_long if side == 1 else rc.swap_short)
    per_oz = side * (px - pos.fill_price) - comm_per_oz + swap
    pos.exit_price, pos.exit_reason, pos.exit_time, pos.status = round(px, 3), reason, when, "CLOSED"
    pos.r_multiple = round(per_oz / pos.risk_per_oz, 4)
    pos.pnl_usd = round(per_oz * rc.contract_size * pos.lots, 2)
    cost_per_oz = rc.spread + rc.slippage * (2 if reason.startswith("SL") else 1) + comm_per_oz - swap
    pos.costs_usd = round(cost_per_oz * rc.contract_size * pos.lots, 2)
    pos.mfe_r, pos.mae_r = round(pos.mfe_r, 3), round(pos.mae_r, 3)
