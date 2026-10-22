"""
Cost-aware, bar-by-bar backtester.

Execution model (conservative, no look-ahead):
  * a decision is made on the CLOSE of bar i using data ≤ i only;
  * entry is a market fill at the OPEN of bar i+1 (the user enters manually
    after the alert) — skipped if that open is outside the entry zone;
  * feed prices are treated as mid; BUY fills at ask (+spread/2) and exits at
    bid, SELL the opposite; stop fills get extra slippage, TP limits do not;
  * if SL and TP are both touched inside one bar → SL (no tick data);
  * a gap through the SL exits at the (worse) open;
  * time exit at the close after ``max_hold_bars``;
  * one position at a time, so the same setup is never counted twice.

Results are in R (multiples of planned risk = |entry − SL|) and, for
drawdown, a fixed-fractional equity curve at ``risk_pct`` per trade.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from strategy.config import RiskConfig, StrategyConfig
from strategy.engine import BUY, SELL, evaluate_bar


@dataclass
class Trade:
    direction: str
    signal_time: str
    entry_time: str
    exit_time: str
    entry_ref: float
    fill: float
    sl: float
    tp: float
    exit_price: float
    exit_reason: str
    risk: float
    r: float
    cost_r: float
    bars_held: int
    regime: str
    score: Optional[float]


DecisionFn = Callable[[int], Optional[Dict[str, Any]]]


def simulate(
    p: pd.DataFrame,
    decide: DecisionFn,
    risk_cfg: RiskConfig,
    max_hold_bars: int,
    start: int = 0,
    end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    ``decide(i)`` returns None or a dict with keys
    action, entry, stop_loss, take_profit, entry_zone (optional), regime, signal_score.
    """
    o, h, l, c = (p[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    ts = p["timestamp"].astype(str).to_numpy()
    n = len(p) if end is None else min(end, len(p))
    half = risk_cfg.spread / 2.0
    slip = risk_cfg.slippage
    comm = risk_cfg.commission_per_lot / risk_cfg.contract_size  # price units per oz

    trades: List[Trade] = []
    signals = 0
    skipped: Counter = Counter()
    no_trade_codes: Counter = Counter()
    i = start
    while i < n - 1:
        d = decide(i)
        if d is None or d.get("action") not in (BUY, SELL):
            for code in (d or {}).get("reason_codes", []) or []:
                no_trade_codes[code] += 1
            i += 1
            continue
        signals += 1
        side = 1 if d["action"] == BUY else -1
        sl, tp, ref = float(d["stop_loss"]), float(d["take_profit"]), float(d["entry"])
        risk = abs(ref - sl)
        j = i + 1
        zone = d.get("entry_zone")
        if zone and not (zone["low"] <= o[j] <= zone["high"]):
            skipped["ENTRY_ZONE_MISSED"] += 1
            i += 1
            continue
        if (side == 1 and o[j] <= sl) or (side == -1 and o[j] >= sl) \
                or (side == 1 and o[j] >= tp) or (side == -1 and o[j] <= tp):
            skipped["OPENED_BEYOND_LEVELS"] += 1
            i += 1
            continue
        fill = o[j] + side * (half + slip)

        exit_price, reason, k = None, None, j
        last = min(j + max_hold_bars - 1, n - 1)
        for k in range(j, last + 1):
            # the exit side is bid for a long, ask for a short: mid ∓ half spread
            lo_exit, hi_exit, open_exit = l[k] - side * half, h[k] - side * half, o[k] - side * half
            if k > j:  # gap through stop at the open
                if (side == 1 and open_exit <= sl) or (side == -1 and open_exit >= sl):
                    exit_price, reason = open_exit - side * slip, "SL_GAP"
                    break
            sl_hit = (lo_exit <= sl) if side == 1 else (hi_exit >= sl)
            tp_hit = (hi_exit >= tp) if side == 1 else (lo_exit <= tp)
            if sl_hit:  # SL first when both touched (conservative)
                exit_price, reason = sl - side * slip, "SL" if not tp_hit else "SL_AMBIGUOUS"
                break
            if tp_hit:
                exit_price, reason = tp, "TP"
                break
        if exit_price is None:
            k = last
            reason = "TIME" if last - j + 1 == max_hold_bars else "OPEN_AT_END"
            exit_price = c[k] - side * half

        pnl = side * (exit_price - fill) - comm
        r = pnl / risk if risk > 0 else 0.0
        cost = 2 * half + slip + (slip if reason.startswith("SL") else 0.0) + comm
        cost_r = cost / risk if risk > 0 else 0.0
        trades.append(Trade(
            direction=d["action"], signal_time=ts[i], entry_time=ts[j], exit_time=ts[k],
            entry_ref=ref, fill=round(fill, 3), sl=sl, tp=tp, exit_price=round(exit_price, 3),
            exit_reason=reason, risk=round(risk, 3), r=round(r, 4), cost_r=round(cost_r, 4),
            bars_held=k - j + 1, regime=d.get("regime", ""), score=d.get("signal_score"),
        ))
        i = k  # flat again after bar k; the next decision may use bar k's close
    return {"trades": trades, "signals": signals, "skipped": dict(skipped),
            "no_trade_codes": dict(no_trade_codes)}


def metrics(trades: List[Trade], risk_pct: float = 0.5) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "note": "Ma'lumot yetarli emas — savdo yo'q"}
    rs = np.array([t.r for t in trades])
    wins, losses = rs[rs > 0], rs[rs <= 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()
    cum = np.cumsum(rs)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd_r = float((peak - cum).max())
    eq = np.cumprod(1 + rs * risk_pct / 100.0)
    eq_peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd_pct = float(((eq_peak - eq) / eq_peak).max() * 100)
    streak = best = 0
    for r in rs:
        streak = streak + 1 if r <= 0 else 0
        best = max(best, streak)
    cost_r = np.array([t.cost_r for t in trades])
    se = float(rs.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    buckets = Counter()
    for r in rs:
        key = "≤-1R" if r <= -0.999 else "-1..0R" if r <= 0 else "0..1R" if r < 1 else "1..2R" if r < 2 else "≥2R"
        buckets[key] += 1
    return {
        "trades": n,
        "win_rate": round(float((rs > 0).mean()) * 100, 1),
        "profit_factor": round(float(gross_win / gross_loss), 2) if gross_loss > 0 else None,
        "expectancy_r": round(float(rs.mean()), 3),
        "expectancy_r_se": round(se, 3) if np.isfinite(se) else None,
        "expectancy_r_gross": round(float((rs + cost_r).mean()), 3),
        "avg_win_r": round(float(wins.mean()), 3) if len(wins) else None,
        "avg_loss_r": round(float(losses.mean()), 3) if len(losses) else None,
        "total_r": round(float(rs.sum()), 2),
        "total_cost_r": round(float(cost_r.sum()), 2),
        "max_drawdown_r": round(dd_r, 2),
        "max_drawdown_pct": round(dd_pct, 2),
        "risk_pct_assumed": risk_pct,
        "max_consecutive_losses": int(best),
        "r_distribution": dict(buckets),
        "exit_reasons": dict(Counter(t.exit_reason for t in trades)),
        "avg_bars_held": round(float(np.mean([t.bars_held for t in trades])), 1),
    }


def breakdown(trades: List[Trade], key: Callable[[Trade], str], risk_pct: float = 0.5) -> Dict[str, Any]:
    groups: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        groups[key(t)].append(t)
    out = {}
    for k in sorted(groups):
        m = metrics(groups[k], risk_pct)
        out[k] = {x: m.get(x) for x in ("trades", "win_rate", "profit_factor", "expectancy_r", "max_drawdown_r")}
    return out


def v2_decider(p: pd.DataFrame, cfg: StrategyConfig, risk_cfg: RiskConfig) -> DecisionFn:
    def decide(i: int):
        return evaluate_bar(p, i, cfg, risk_cfg).to_dict()
    return decide


def run_v2(p: pd.DataFrame, cfg: StrategyConfig, risk_cfg: RiskConfig,
           start: int = 0, end: Optional[int] = None) -> Dict[str, Any]:
    res = simulate(p, v2_decider(p, cfg, risk_cfg), risk_cfg, cfg.max_hold_bars, start, end)
    res["metrics"] = metrics(res["trades"], risk_cfg.risk_pct)
    return res
