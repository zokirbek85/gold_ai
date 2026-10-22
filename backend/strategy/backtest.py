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
    mfe_r: float = 0.0          # max favourable excursion (R, mid prices)
    mae_r: float = 0.0          # max adverse excursion (R, mid prices)
    swap_r: float = 0.0
    nights: int = 0
    strategy: str = ""


def _nights(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> int:
    """Rollovers (21:00 UTC) crossed while open; Wednesday counts triple (weekend swap)."""
    n, t = 0, entry_ts.normalize() + pd.Timedelta(hours=21)
    if t <= entry_ts:
        t += pd.Timedelta(days=1)
    while t < exit_ts:
        if t.dayofweek < 5:
            n += 3 if t.dayofweek == 2 else 1
        t += pd.Timedelta(days=1)
    return n


DecisionFn = Callable[[int], Optional[Dict[str, Any]]]


def fill_price(side: int, open_mid: float, half: float, slip: float) -> float:
    """Market entry: a long buys at ask (+half spread) plus slippage; a short the opposite."""
    return open_mid + side * (half + slip)


def step_exit(side: int, o: float, h: float, l: float, sl: float, tp: float,
              half: float, slip: float, gap_check: bool = True):
    """
    One bar of position management, shared by the backtester and the paper broker.
    The exit side is bid for a long and ask for a short (mid ∓ half spread).
    Returns (exit_price, reason) or (None, None).
    """
    lo_exit, hi_exit, open_exit = l - side * half, h - side * half, o - side * half
    if gap_check and ((side == 1 and open_exit <= sl) or (side == -1 and open_exit >= sl)):
        return open_exit - side * slip, "SL_GAP"
    sl_hit = (lo_exit <= sl) if side == 1 else (hi_exit >= sl)
    tp_hit = (hi_exit >= tp) if side == 1 else (lo_exit <= tp)
    if sl_hit:  # SL first when both are touched inside one bar (no tick data)
        return sl - side * slip, ("SL_AMBIGUOUS" if tp_hit else "SL")
    if tp_hit:
        return tp, "TP"
    return None, None


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
        fill = fill_price(side, o[j], half, slip)

        exit_price, reason, k = None, None, j
        last = min(j + max_hold_bars - 1, n - 1)
        for k in range(j, last + 1):
            exit_price, reason = step_exit(side, o[k], h[k], l[k], sl, tp, half, slip, gap_check=k > j)
            if exit_price is not None:
                break
        if exit_price is None:
            k = last
            reason = "TIME" if last - j + 1 == max_hold_bars else "OPEN_AT_END"
            exit_price = c[k] - side * half

        t_in, t_out = pd.Timestamp(ts[j]), pd.Timestamp(ts[k])
        tf_delta = (pd.Timestamp(ts[min(k + 1, len(ts) - 1)]) - t_out) if k + 1 < len(ts) else pd.Timedelta(0)
        nights = _nights(t_in, t_out + max(tf_delta, pd.Timedelta(0)))
        swap = nights * (risk_cfg.swap_long if side == 1 else risk_cfg.swap_short)
        pnl = side * (exit_price - fill) - comm + swap
        r = pnl / risk if risk > 0 else 0.0
        cost = 2 * half + slip + (slip if reason.startswith("SL") else 0.0) + comm - swap
        cost_r = cost / risk if risk > 0 else 0.0
        if side == 1:
            mfe, mae = h[j:k + 1].max() - fill, fill - l[j:k + 1].min()
        else:
            mfe, mae = fill - l[j:k + 1].min(), h[j:k + 1].max() - fill
        trades.append(Trade(
            direction=d["action"], signal_time=ts[i], entry_time=ts[j], exit_time=ts[k],
            entry_ref=ref, fill=round(fill, 3), sl=sl, tp=tp, exit_price=round(exit_price, 3),
            exit_reason=reason, risk=round(risk, 3), r=round(r, 4), cost_r=round(cost_r, 4),
            bars_held=k - j + 1, regime=d.get("regime", ""), score=d.get("signal_score"),
            mfe_r=round(max(mfe, 0.0) / risk, 3) if risk > 0 else 0.0,
            mae_r=round(max(mae, 0.0) / risk, 3) if risk > 0 else 0.0,
            swap_r=round(swap / risk, 4) if risk > 0 else 0.0, nights=nights,
            strategy=d.get("strategy", ""),
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
    rng = np.random.default_rng(12345)
    boot = rng.choice(rs, size=(2000, n), replace=True).mean(axis=1) if n > 1 else np.array([rs.mean()])
    ci_lo, ci_hi = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))
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
        "expectancy_r_ci95": [round(ci_lo, 3), round(ci_hi, 3)],
        "expectancy_r_gross": round(float((rs + cost_r).mean()), 3),
        "avg_mfe_r": round(float(np.mean([getattr(t, "mfe_r", 0.0) for t in trades])), 3),
        "avg_mae_r": round(float(np.mean([getattr(t, "mae_r", 0.0) for t in trades])), 3),
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
