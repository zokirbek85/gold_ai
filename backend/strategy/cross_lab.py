"""
Cross-asset + bear/sideways laboratory (2026-11-18).

PRE-REGISTERED PROTOCOL — fixed before the first run. No parameter is tuned; all
strategy parameters are the frozen ones from strategy/lab.py and strategy/vol_lab.py.

Why: (1) gold's D1 trend turned DOWN in Nov 2026 while every edge found so far
came from the 2024–26 gold bull market; (2) one instrument gives ~1–3 trades a
month. Testing the SAME rules on other liquid markets is new out-of-sample
evidence and, if they work there too, more independent trades.

Instruments (Twelvedata, H1 + H4, 2020-01 → 2026-11; D1 resampled from H4):
  XAUUSD  scale 1      spread 0.30  slippage 0.10  max_spread 0.60   (USD)
  EURUSD  scale 10000  spread 1.0   slippage 0.2   max_spread 2.0    (pips)
  GBPUSD  scale 10000  spread 1.2   slippage 0.2   max_spread 2.4    (pips)
  USDJPY  scale 100    spread 1.0   slippage 0.2   max_spread 2.0    (pips)
  Prices are scaled so the engine's 2-decimal level rounding is harmless; R
  multiples are scale-invariant. Silver (XAG/USD) needs a paid data plan → not tested.
  Swap = 0 (unknown) everywhere, as in all earlier studies.

Strategies (frozen):
  trend_pullback  H4/D1  v2 champion
  donchian_break  H4/D1  lab.py
  squeeze_trend   H1/D1  vol_lab.py
  range_fade      H1/D1  NEW bear/sideways hypothesis: lab.py mean_reversion rule
                         (RANGE regime, close outside BB(20,2), RSI 30/70, reversal
                         candle, SL 1.5 ATR, TP = BB mid) ONLY when D1 has no trend.

Control: random entries with matched frequency, 20 seeds — D1-trend direction for
the trend strategies; random direction while D1 has no trend for range_fade.
SL 1.5 ATR, TP 2.5 R (range_fade control: TP 1 R).

Splits: H1 train < 2024-01-01 ≤ test; H4 train < 2024-07-01 ≤ test.

Acceptance per (instrument, strategy), ALL required:
  1. test trades ≥ 30            2. test expectancy CI95 low > 0
  3. train expectancy > 0        4. test expectancy > control p90
  5. test max drawdown ≤ 6 % at 0.5 % risk
A strategy is called ROBUST only if accepted on ≥ 2 of the 4 instruments
(16 tests are run; at a 5 % false-positive rate ~1 lucky pass is expected).

    python -m strategy.cross_lab --data <dir with td_/eur_/gbp_/jpy_ 1h,4h csv> --now … --out cross_lab.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, Dict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import STRATEGY_VERSION  # noqa: E402
from strategy.backtest import breakdown, simulate  # noqa: E402
from strategy.config import RiskConfig  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402
from strategy.engine import BUY, SELL, attach_context, classify_regime, prepare_context, prepare_primary  # noqa: E402
from strategy.lab import _common_block, _finalize, default_cfg, make_decider  # noqa: E402
from strategy.research import resample  # noqa: E402
from strategy.vol_lab import MAX_DD_PCT, _idx, _m, squeeze_trend  # noqa: E402

H1_SPLIT, H4_SPLIT = "2024-01-01", "2024-07-01"
SEEDS = 20
INSTRUMENTS = {
    "XAUUSD": {"prefix": "td", "scale": 1.0, "spread": 0.30, "slippage": 0.10, "max_spread": 0.60},
    "EURUSD": {"prefix": "eur", "scale": 10000.0, "spread": 1.0, "slippage": 0.2, "max_spread": 2.0},
    "GBPUSD": {"prefix": "gbp", "scale": 10000.0, "spread": 1.2, "slippage": 0.2, "max_spread": 2.4},
    "USDJPY": {"prefix": "jpy", "scale": 100.0, "spread": 1.0, "slippage": 0.2, "max_spread": 2.0},
}


def range_fade(p, cfg, rc):
    base = make_decider("mean_reversion", p, cfg, rc)
    trend = p["c_trend"].to_numpy()

    def d(i):
        if trend[i] != "NONE":
            return {"action": "NO TRADE", "reason_codes": ["D1_TRENDING"]}
        return base(i)
    return d


STRATEGIES = {
    "trend_pullback": ("H4", lambda p, cfg, rc: make_decider("trend_pullback", p, cfg, rc), "trend"),
    "donchian_break": ("H4", lambda p, cfg, rc: make_decider("donchian_break", p, cfg, rc), "trend"),
    "squeeze_trend": ("H1", squeeze_trend, "trend"),
    "range_fade": ("H1", range_fade, "none"),
}


def control(p, cfg, rc, prob, seed, mode):
    rng = np.random.default_rng(seed)
    draws, sides = rng.random(len(p)), rng.random(len(p))
    trend, c, atr = p["c_trend"].to_numpy(), p["close"].to_numpy(), p["atr"].to_numpy()
    rr = 2.5 if mode == "trend" else 1.0

    def d(i):
        if draws[i] >= prob or not np.isfinite(atr[i]):
            return None
        if mode == "trend":
            if trend[i] not in ("UP", "DOWN"):
                return None
            side = BUY if trend[i] == "UP" else SELL
        else:
            if trend[i] != "NONE":
                return None
            side = BUY if sides[i] < 0.5 else SELL
        row = p.iloc[i]
        if _common_block(row, cfg, rc):
            return None
        return _finalize(side, c[i], 1.5 * atr[i], rr, row, cfg, rc, "control", classify_regime(row, cfg))
    return d


def load(data_dir: str, inst: Dict[str, Any], now: datetime):
    def rd(tf):
        df = pd.read_csv(os.path.join(data_dir, f"{inst['prefix']}_{tf}.csv"))
        for k in ("open", "high", "low", "close"):
            df[k] = df[k] * inst["scale"]
        return df
    h1, r1 = clean_candles(rd("1h"), 60, now)
    h4, r4 = clean_candles(rd("4h"), 240, now)
    d1, _ = clean_candles(resample(h4, 1440), 1440, now)
    c4, c1 = default_cfg(240, 1440), default_cfg(60, 1440)
    p4 = attach_context(prepare_primary(h4, c4), prepare_context(d1, c4))
    p1 = attach_context(prepare_primary(h1, c1), prepare_context(d1, c1))
    return {"H4": (p4, c4, H4_SPLIT), "H1": (p1, c1, H1_SPLIT)}, {"h1": r1.to_dict(), "h4": r4.to_dict()}


def evaluate(p, cfg, rc, split_ts, build, mode) -> Dict[str, Any]:
    warm, split, n = cfg.min_history_bars, _idx(p, split_ts), len(p)
    dec = build(p, cfg, rc)
    tr = simulate(p, dec, rc, cfg.max_hold_bars, warm, split)["trades"]
    te = simulate(p, dec, rc, cfg.max_hold_bars, split, n)["trades"]
    full = tr + te
    ctx = p["c_trend"].to_numpy()
    ts = p["timestamp"].astype(str).to_numpy()
    ctx_at = dict(zip(ts, ctx))
    res = {"train": _m(tr, rc), "test": _m(te, rc),
           "by_year": breakdown(full, lambda t: t.entry_time[:4], rc.risk_pct),
           "by_direction": breakdown(full, lambda t: t.direction, rc.risk_pct),
           "by_d1_trend_at_signal": breakdown(full, lambda t: str(ctx_at.get(t.signal_time, "?")), rc.risk_pct),
           "trades_per_month": round(len(full) / max(1, (p.timestamp.iloc[-1] - p.timestamp.iloc[warm]).days / 30.4), 2)}
    prob = min(1.0, max(len(te), 1) * 1.6 / max(1, n - split))
    exps = []
    for s in range(SEEDS):
        ct = simulate(p, control(p, cfg, rc, prob, s, mode), rc, cfg.max_hold_bars, split, n)["trades"]
        if ct:
            exps.append(float(np.mean([t.r for t in ct])))
    res["control_test"] = {"seeds": len(exps),
                           "p50": round(float(np.percentile(exps, 50)), 3) if exps else None,
                           "p90": round(float(np.percentile(exps, 90)), 3) if exps else None}
    t = res["test"]
    ci = t.get("expectancy_r_ci95") or [None, None]
    checks = {"test_trades_ge_30": (t["trades"] or 0) >= 30,
              "test_ci95_low_gt_0": ci[0] is not None and ci[0] > 0,
              "train_expectancy_gt_0": (res["train"]["expectancy_r"] or -1) > 0,
              "beats_control_p90": bool(exps) and (t["expectancy_r"] or -9) > res["control_test"]["p90"],
              "test_max_dd_le_6pct": (t["max_drawdown_pct"] or 99) <= MAX_DD_PCT}
    res["acceptance"] = {"checks": checks, "passed": all(checks.values())}
    res["_returns"] = [(x.exit_time, x.r) for x in te]
    return res


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--out", default="cross_lab.json")
    a = ap.parse_args()
    now = datetime.fromisoformat(a.now)
    out: Dict[str, Any] = {"strategy_version": STRATEGY_VERSION, "generated_at": datetime.utcnow().isoformat() + "Z",
                           "protocol": (__doc__ or "").strip(), "instruments": {}, "results": {}}
    for sym, inst in INSTRUMENTS.items():
        rc = replace(RiskConfig(), spread=inst["spread"], slippage=inst["slippage"], max_spread=inst["max_spread"],
                     swap_long=0.0, swap_short=0.0)
        frames, quality = load(a.data, inst, now)
        out["instruments"][sym] = {**inst, "risk_config": asdict(rc), "quality": quality,
                                   "h1": [str(frames["H1"][0].timestamp.iloc[0]), str(frames["H1"][0].timestamp.iloc[-1])]}
        for name, (tf, build, mode) in STRATEGIES.items():
            p, cfg, split = frames[tf]
            r = evaluate(p, cfg, rc, split, build, mode)
            out["results"].setdefault(name, {})[sym] = r
            t = r["test"]
            print(f"{sym} {name:15s} TRAIN n={r['train']['trades']} exp={r['train']['expectancy_r']} | TEST n={t['trades']} "
                  f"exp={t['expectancy_r']} ci={t['expectancy_r_ci95']} dd={t['max_drawdown_pct']}% | ctrl p90={r['control_test']['p90']} "
                  f"| PASS={r['acceptance']['passed']}", flush=True)

    summary = {}
    for name, per in out["results"].items():
        passed = [s for s, r in per.items() if r["acceptance"]["passed"]]
        # equal-weight pooled test trades across instruments (diversification view, not an acceptance test)
        pooled = sorted([x for r in per.values() for x in r["_returns"]])
        rs = np.array([x[1] for x in pooled]) if pooled else np.array([])
        summary[name] = {"accepted_on": passed, "robust": len(passed) >= 2,
                         "pooled_test_trades": int(rs.size),
                         "pooled_test_expectancy_r": round(float(rs.mean()), 3) if rs.size else None,
                         "pooled_test_ci95": [round(float(rs.mean() - 1.96 * rs.std(ddof=1) / np.sqrt(rs.size)), 3),
                                              round(float(rs.mean() + 1.96 * rs.std(ddof=1) / np.sqrt(rs.size)), 3)]
                         if rs.size > 1 else None}
        for r in per.values():
            r.pop("_returns", None)
    out["summary"] = summary
    print(json.dumps(summary, indent=1))
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
