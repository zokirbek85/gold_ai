"""
Volatility-candidate laboratory (phase 3, 2026-11-18).

PRE-REGISTERED PROTOCOL — written before the first run; parameters are textbook
defaults, NOT tuned. Changing anything after seeing results requires a new,
separately reported study.

Data: Twelvedata XAU/USD H1 2020-01 → 2026-11 and H4; D1 resampled from H4.
Harness: strategy.backtest.simulate (next-bar-open entry, SL first inside a bar,
one position at a time, RiskConfig spread/slippage/swap) — identical to lab.py.

Candidates
  squeeze_trend   H1 primary, D1 context. Prior bar BB(20,2)-width in the bottom
                  20 % of 100 bars, close beyond the prior 20-bar high/low, ONLY in
                  the D1 trend direction. SL 1.5 ATR, TP 2.5 R.
  london_orb      H1 primary, D1 context. Range = the H1 bar opening 07:00 UTC.
                  First H1 close of the day in 08:00–11:59 beyond range ± 0.1 ATR,
                  D1 trend not opposing. SL = other side of the range (bounded by
                  sl_min/max ATR), TP 2 R. One breakout per day.
  pullback_atrband  The H4/D1 champion (trend_pullback) traded only when
                  ATR / ATR-median is inside [0.8, 1.5].

Control
  random_trend    Random entries in the D1 trend direction, SL 1.5 ATR, TP 2.5 R,
                  entry probability matched to the candidate's trade count;
                  30 seeds. Measures how much of a result is just "trade with the
                  D1 trend in a bull market".

Splits: H1 train < 2024-01-01 ≤ test.  H4 train < 2024-07-01 ≤ test (as lab.py).

Acceptance (ALL required before a candidate may enter paper trading):
  1. test trades ≥ 30
  2. test expectancy CI95 lower bound > 0
  3. train expectancy > 0
  4. test expectancy > 90th percentile of its random_trend control
  5. test max drawdown ≤ 6 % at 0.5 % risk (2× champion)

    python -m strategy.vol_lab --h1 td_1h.csv --h4 td_4h.csv --now 2026-11-18T12:00:00 --out vol_lab.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import STRATEGY_VERSION  # noqa: E402
from strategy.backtest import breakdown, metrics, simulate  # noqa: E402
from strategy.config import RiskConfig  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402
from strategy.engine import BUY, SELL, attach_context, classify_regime, evaluate_bar, prepare_context, prepare_primary  # noqa: E402
from strategy.lab import _common_block, _finalize, default_cfg, enrich, make_decider  # noqa: E402
from strategy.research import resample  # noqa: E402

H1_SPLIT, H4_SPLIT = "2024-01-01", "2024-07-01"
SQUEEZE_PCT, SQUEEZE_SL, SQUEEZE_RR = 0.2, 1.5, 2.5
ORB_HOUR, ORB_LAST_HOUR, ORB_BUF_ATR, ORB_RR = 7, 11, 0.1, 2.0
ATR_BAND = (0.8, 1.5)
CONTROL_SEEDS, CONTROL_SL, CONTROL_RR = 30, 1.5, 2.5
MAX_DD_PCT = 6.0
KEYS = ("trades", "win_rate", "profit_factor", "expectancy_r", "expectancy_r_ci95", "max_drawdown_pct",
        "max_consecutive_losses", "avg_win_r", "avg_loss_r", "avg_mfe_r", "total_cost_r")


def _m(trades, rc):
    m = metrics(trades, rc.risk_pct)
    return {k: m.get(k) for k in KEYS}


def _idx(p, ts):
    return int((p["timestamp"] < pd.Timestamp(ts)).sum())


# ── candidate deciders ───────────────────────────────────────────────────────

def squeeze_trend(p, cfg, rc):
    x = enrich(p)
    c, atr, hi, lo, w = (x[k].to_numpy() for k in ("close", "atr", "don_hi", "don_lo", "bb_width_pct"))
    trend = x["c_trend"].to_numpy()

    def d(i):
        if i < 2 or np.isnan(w[i - 1]) or np.isnan(hi[i]):
            return None
        row = x.iloc[i]
        blk = _common_block(row, cfg, rc)
        if blk:
            return {"action": "NO TRADE", "reason_codes": [blk]}
        if w[i - 1] > SQUEEZE_PCT:
            return {"action": "NO TRADE", "reason_codes": ["NO_SQUEEZE"]}
        reg = classify_regime(row, cfg)
        if c[i] > hi[i] and trend[i] == "UP":
            return _finalize(BUY, c[i], SQUEEZE_SL * atr[i], SQUEEZE_RR, row, cfg, rc, "squeeze_trend", reg)
        if c[i] < lo[i] and trend[i] == "DOWN":
            return _finalize(SELL, c[i], SQUEEZE_SL * atr[i], SQUEEZE_RR, row, cfg, rc, "squeeze_trend", reg)
        return {"action": "NO TRADE", "reason_codes": ["NO_BREAKOUT_WITH_TREND"]}
    return d


def london_orb(p, cfg, rc):
    ts = pd.to_datetime(p["timestamp"])
    hour, day = ts.dt.hour.to_numpy(), ts.dt.normalize().to_numpy()
    o, h, l, c, atr = (p[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    trend = p["c_trend"].to_numpy()
    # causal precompute: the opening-range bar of each day and the FIRST breakout bar after it
    signal: Dict[int, str] = {}
    rng: Dict[Any, tuple] = {}
    done = set()
    for i in range(len(p)):
        if hour[i] == ORB_HOUR:
            rng[day[i]] = (h[i], l[i])
        elif ORB_HOUR < hour[i] <= ORB_LAST_HOUR and day[i] in rng and day[i] not in done and np.isfinite(atr[i]):
            rh, rl = rng[day[i]]
            buf = ORB_BUF_ATR * atr[i]
            if c[i] > rh + buf:
                signal[i] = BUY
                done.add(day[i])
            elif c[i] < rl - buf:
                signal[i] = SELL
                done.add(day[i])

    def d(i):
        side = signal.get(i)
        if side is None:
            return None
        row = p.iloc[i]
        blk = _common_block(row, cfg, rc)
        if blk:
            return {"action": "NO TRADE", "reason_codes": [blk]}
        if (side == BUY and trend[i] == "DOWN") or (side == SELL and trend[i] == "UP"):
            return {"action": "NO TRADE", "reason_codes": ["AGAINST_D1_TREND"]}
        rh, rl = rng[day[i]]
        risk = c[i] - rl if side == BUY else rh - c[i]
        return _finalize(side, c[i], risk, ORB_RR, row, cfg, rc, "london_orb", classify_regime(row, cfg))
    return d


def pullback_atrband(p, cfg, rc):
    ratio = (p["atr"] / p["atr_med"]).to_numpy()

    def d(i):
        out = evaluate_bar(p, i, cfg, rc).to_dict()
        out["strategy"] = "pullback_atrband"
        if out.get("action") in (BUY, SELL) and not (ATR_BAND[0] <= ratio[i] <= ATR_BAND[1]):
            return {"action": "NO TRADE", "reason_codes": ["ATR_OUTSIDE_BAND"]}
        return out
    return d


def random_trend(p, cfg, rc, prob: float, seed: int):
    rng = np.random.default_rng(seed)
    draws = rng.random(len(p))
    trend, c, atr = p["c_trend"].to_numpy(), p["close"].to_numpy(), p["atr"].to_numpy()

    def d(i):
        if draws[i] >= prob or trend[i] not in ("UP", "DOWN") or not np.isfinite(atr[i]):
            return None
        row = p.iloc[i]
        if _common_block(row, cfg, rc):
            return None
        side = BUY if trend[i] == "UP" else SELL
        return _finalize(side, c[i], CONTROL_SL * atr[i], CONTROL_RR, row, cfg, rc, "random_trend", classify_regime(row, cfg))
    return d


CANDIDATES = {"squeeze_trend": ("H1", squeeze_trend), "london_orb": ("H1", london_orb),
              "pullback_atrband": ("H4", pullback_atrband)}


# ── study ────────────────────────────────────────────────────────────────────

def _overlap(a: List, b: List) -> float:
    """Share of trades in ``a`` whose holding period overlaps any trade in ``b``."""
    if not a or not b:
        return 0.0
    iv = sorted((pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)) for t in b)
    n = 0
    for t in a:
        s, e = pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)
        n += any(bs <= e and s <= be for bs, be in iv)
    return round(n / len(a), 3)


def evaluate(name, p, cfg, rc, split_ts, champion_trades):
    _, build = CANDIDATES[name]
    warm, split, n = cfg.min_history_bars, _idx(p, split_ts), len(p)
    dec = build(p, cfg, rc)
    tr = simulate(p, dec, rc, cfg.max_hold_bars, warm, split)["trades"]
    te = simulate(p, dec, rc, cfg.max_hold_bars, split, n)["trades"]
    full = tr + te
    res = {"train": _m(tr, rc), "test": _m(te, rc),
           "by_year": breakdown(full, lambda t: t.entry_time[:4], rc.risk_pct),
           "by_direction": breakdown(full, lambda t: t.direction, rc.risk_pct),
           "test_by_regime": breakdown(te, lambda t: t.regime, rc.risk_pct),
           "trades_per_month": round(len(full) / max(1, (p.timestamp.iloc[-1] - p.timestamp.iloc[warm]).days / 30.4), 2),
           "overlap_with_champion": _overlap(full, champion_trades)}

    # random control with matched frequency (test period)
    bars = max(1, n - split)
    prob = min(1.0, max(len(te), 1) * 1.6 / bars)   # ×1.6: many draws are skipped while a trade is open
    ctrl = []
    for s in range(CONTROL_SEEDS):
        ct = simulate(p, random_trend(p, cfg, rc, prob, s), rc, cfg.max_hold_bars, split, n)["trades"]
        if ct:
            ctrl.append((len(ct), float(np.mean([t.r for t in ct]))))
    exps = [e for _, e in ctrl]
    res["control_test"] = {"seeds": len(ctrl), "avg_trades": round(float(np.mean([k for k, _ in ctrl])), 1) if ctrl else 0,
                           "expectancy_p50": round(float(np.percentile(exps, 50)), 3) if exps else None,
                           "expectancy_p90": round(float(np.percentile(exps, 90)), 3) if exps else None}

    t = res["test"]
    ci = t.get("expectancy_r_ci95") or [None, None]
    checks = {
        "test_trades_ge_30": (t["trades"] or 0) >= 30,
        "test_ci95_low_gt_0": ci[0] is not None and ci[0] > 0,
        "train_expectancy_gt_0": (res["train"]["expectancy_r"] or -1) > 0,
        "beats_random_p90": exps != [] and (t["expectancy_r"] or -9) > res["control_test"]["expectancy_p90"],
        "test_max_dd_le_6pct": (t["max_drawdown_pct"] or 99) <= MAX_DD_PCT,
    }
    res["acceptance"] = {"checks": checks, "passed": all(checks.values())}
    return res


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--h4", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--out", default="vol_lab.json")
    a = ap.parse_args()
    now = datetime.fromisoformat(a.now)
    rc = RiskConfig()

    h4, rep4 = clean_candles(pd.read_csv(a.h4), 240, now)
    h1, rep1 = clean_candles(pd.read_csv(a.h1), 60, now)
    d1, _ = clean_candles(resample(h4, 1440), 1440, now)

    cfg4 = default_cfg(240, 1440)
    p4 = attach_context(prepare_primary(h4, cfg4), prepare_context(d1, cfg4))
    cfg1 = default_cfg(60, 1440)
    p1 = attach_context(prepare_primary(h1, cfg1), prepare_context(d1, cfg1))

    champ = simulate(p4, make_decider("trend_pullback", p4, cfg4, rc), rc, cfg4.max_hold_bars,
                     cfg4.min_history_bars, len(p4))["trades"]
    sp4 = _idx(p4, H4_SPLIT)
    out: Dict[str, Any] = {
        "strategy_version": STRATEGY_VERSION, "generated_at": datetime.utcnow().isoformat() + "Z",
        "protocol": (__doc__ or "").strip(), "risk_config": asdict(rc),
        "data": {"h1": [str(h1.timestamp.iloc[0]), str(h1.timestamp.iloc[-1]), len(h1)],
                 "h4": [str(h4.timestamp.iloc[0]), str(h4.timestamp.iloc[-1]), len(h4)],
                 "quality": {"h1": rep1.to_dict(), "h4": rep4.to_dict()}},
        "champion_reference": {"train": _m([t for t in champ if t.entry_time < H4_SPLIT], rc),
                               "test": _m([t for t in champ if t.entry_time >= H4_SPLIT], rc)},
        "candidates": {},
    }
    for name, (tf, _) in CANDIDATES.items():
        p, cfg, split = (p1, cfg1, H1_SPLIT) if tf == "H1" else (p4, cfg4, H4_SPLIT)
        out["candidates"][name] = {"timeframe": f"{tf}/D1", "split": split, **evaluate(name, p, cfg, rc, split, champ)}
        r = out["candidates"][name]
        print(f"{name:17s} TRAIN n={r['train']['trades']} exp={r['train']['expectancy_r']} | TEST n={r['test']['trades']} "
              f"exp={r['test']['expectancy_r']} ci={r['test']['expectancy_r_ci95']} dd={r['test']['max_drawdown_pct']}% "
              f"| ctrl p50/p90={r['control_test']['expectancy_p50']}/{r['control_test']['expectancy_p90']} "
              f"| overlap={r['overlap_with_champion']} | PASS={r['acceptance']['passed']}", flush=True)
    print("champion", out["champion_reference"]["test"])
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
