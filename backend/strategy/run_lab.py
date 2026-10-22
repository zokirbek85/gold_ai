"""
Run the strategy laboratory and the regime study.

    ML_MODEL_DIR=/tmp/empty python -m strategy.run_lab \
        --h1 td_1h.csv --h4 td_4h.csv --now 2026-10-22T07:00:00 --out lab.json

Split rules are fixed: H4 train < 2024-07-01 ≤ test; H1 train < 2025-04-01 ≤ test.
The regime router is fitted on train only (and re-fitted per walk-forward window).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import asdict, replace
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import STRATEGY_VERSION  # noqa: E402
from strategy.backtest import breakdown, metrics, simulate  # noqa: E402
from strategy.config import RiskConfig  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402
from strategy.engine import attach_context, classify_regime, prepare_context, prepare_primary  # noqa: E402
from strategy.lab import FAMILIES, default_cfg, make_decider  # noqa: E402
from strategy.research import resample  # noqa: E402

KEYS = ("trades", "win_rate", "profit_factor", "expectancy_r", "expectancy_r_ci95",
        "max_drawdown_r", "max_drawdown_pct", "max_consecutive_losses", "avg_win_r",
        "avg_loss_r", "avg_mfe_r", "avg_mae_r", "total_cost_r")


def session(ts: str) -> str:
    h = pd.Timestamp(ts).hour
    if h >= 23 or h < 7:
        return "asia"
    if h < 12:
        return "london"
    if h < 16:
        return "london_ny_overlap"
    return "ny_late"


def _idx(p, ts):
    return int((p["timestamp"] < pd.Timestamp(ts)).sum())


def _m(trades, rc):
    m = metrics(trades, rc.risk_pct)
    return {k: m.get(k) for k in KEYS}


def run_family(p, name, cfg, rc, a, b):
    return simulate(p, make_decider(name, p, cfg, rc), rc, cfg.max_hold_bars, a, b)["trades"]


def regime_study(p, cfg):
    """Forward 6-bar move in ATR units by regime (descriptive, not a strategy)."""
    reg = np.array([classify_regime(r, cfg) for _, r in p.iterrows()])
    fwd = (p["close"].shift(-6) - p["close"]) / p["atr"]
    out = {}
    for r in sorted(set(reg)):
        m = (reg == r) & fwd.notna().to_numpy()
        if m.sum() < 30:
            continue
        f = fwd[m]
        out[r] = {"bars": int(m.sum()), "share": round(float(m.mean()), 3),
                  "mean_fwd6_atr": round(float(f.mean()), 3),
                  "abs_fwd6_atr": round(float(f.abs().mean()), 3),
                  "up_share": round(float((f > 0).mean()), 3)}
    return out, reg


def router_decider(p, reg, table, cfg, rc):
    deciders = {n: make_decider(n, p, cfg, rc) for n in set(table.values())}

    def d(i):
        fam = table.get(reg[i])
        if fam is None:
            return {"action": "NO TRADE", "reason_codes": [f"ROUTER_NO_STRATEGY_{reg[i]}"]}
        return deciders[fam](i)
    return d


def fit_router(trades_by_family, min_trades=15):
    """Pick, per regime, the family with the best positive expectancy (train trades only)."""
    best = {}
    for fam, trades in trades_by_family.items():
        by = {}
        for t in trades:
            by.setdefault(t.regime, []).append(t.r)
        for regm, rs in by.items():
            if len(rs) >= min_trades and np.mean(rs) > 0:
                if regm not in best or np.mean(rs) > best[regm][1]:
                    best[regm] = (fam, float(np.mean(rs)), len(rs))
    return {k: v[0] for k, v in best.items()}, {k: {"family": v[0], "train_exp": round(v[1], 3), "n": v[2]} for k, v in best.items()}


def study(p, cfg, rc, split_ts, warm):
    split, n = _idx(p, split_ts), len(p)
    res = {"period": {"train": [str(p.timestamp.iloc[warm]), str(p.timestamp.iloc[split - 1])],
                      "test": [str(p.timestamp.iloc[split]), str(p.timestamp.iloc[-1])]}}
    res["regimes"], reg = regime_study(p, cfg)
    fam_out, train_trades = {}, {}
    for name in FAMILIES:
        tr = run_family(p, name, cfg, rc, warm, split)
        te = run_family(p, name, cfg, rc, split, n)
        full = tr + te
        train_trades[name] = tr
        fam_out[name] = {
            "train": _m(tr, rc), "test": _m(te, rc),
            "test_by_regime": breakdown(te, lambda t: t.regime, rc.risk_pct),
            "full_by_regime": breakdown(full, lambda t: t.regime, rc.risk_pct),
            "full_by_session": breakdown(full, lambda t: session(t.signal_time), rc.risk_pct),
            "full_by_direction": breakdown(full, lambda t: t.direction, rc.risk_pct),
            "full_by_half_year": breakdown(full, lambda t: t.entry_time[:4] + ("H1" if t.entry_time[5:7] <= "06" else "H2"), rc.risk_pct),
            "trades_per_month": round(len(full) / max(1, (pd.Timestamp(p.timestamp.iloc[-1]) - pd.Timestamp(p.timestamp.iloc[warm])).days / 30.4), 2),
        }
    res["families"] = fam_out

    # regime router: fitted on train, evaluated on test
    table, info = fit_router(train_trades)
    rt = simulate(p, router_decider(p, reg, table, cfg, rc), rc, cfg.max_hold_bars, split, n)["trades"]
    res["router"] = {"table": info, "test": _m(rt, rc)}

    # walk-forward router: refit on 24 months, test next 6
    wf, pooled = [], []
    for s in pd.date_range(pd.Timestamp(p.timestamp.iloc[warm]).normalize(), p.timestamp.iloc[-1], freq="6MS"):
        a, b, c = _idx(p, str(s)), _idx(p, str(s + pd.DateOffset(months=24))), _idx(p, str(s + pd.DateOffset(months=30)))
        if b >= n or c - b < 100:
            continue
        tt = {fam: run_family(p, fam, cfg, rc, max(a, warm), b) for fam in FAMILIES}
        tbl, inf = fit_router(tt, min_trades=10)
        oos = simulate(p, router_decider(p, reg, tbl, cfg, rc), rc, cfg.max_hold_bars, b, c)["trades"]
        pooled += [t.r for t in oos]
        wf.append({"fit": [str(s.date()), str((s + pd.DateOffset(months=24)).date())], "table": tbl,
                   "oos_trades": len(oos), "oos_expectancy_r": round(float(np.mean([t.r for t in oos])), 3) if oos else None})
    res["router_walk_forward"] = {"windows": wf, "pooled_trades": len(pooled),
                                  "pooled_expectancy_r": round(float(np.mean(pooled)), 3) if pooled else None}
    return res


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--h4", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--out", default="lab.json")
    args = ap.parse_args()
    now = datetime.fromisoformat(args.now)
    rc = RiskConfig()
    out = {"strategy_version": STRATEGY_VERSION, "generated_at": datetime.utcnow().isoformat() + "Z",
           "risk_config": asdict(rc)}

    h4, _ = clean_candles(pd.read_csv(args.h4), 240, now)
    d1, _ = clean_candles(resample(h4, 1440), 1440, now)
    cfg4 = default_cfg(240, 1440)
    p4 = attach_context(prepare_primary(h4, cfg4), prepare_context(d1, cfg4))
    out["H4_D1"] = study(p4, cfg4, rc, "2024-07-01", cfg4.min_history_bars)

    h1, _ = clean_candles(pd.read_csv(args.h1), 60, now)
    cfg1 = default_cfg(60, 240)
    p1 = attach_context(prepare_primary(h1, cfg1), prepare_context(h4, cfg1))
    out["H1_H4"] = study(p1, cfg1, rc, "2025-04-01", cfg1.min_history_bars)

    # swap sensitivity (assumed USD/oz/night; broker values unknown)
    sens = {}
    for sw in (0.0, -0.25, -0.5):
        rc2 = replace(rc, swap_long=sw, swap_short=sw)
        split = _idx(p4, "2024-07-01")
        sens[f"swap_{sw}"] = {f: _m(run_family(p4, f, cfg4, rc2, split, len(p4)), rc2)["expectancy_r"] for f in FAMILIES}
    out["H4_D1"]["swap_sensitivity_test"] = sens

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    for tf in ("H4_D1", "H1_H4"):
        print("==", tf, out[tf]["period"])
        for fam, v in out[tf]["families"].items():
            print(f"  {fam:15s} TRAIN", {k: v["train"][k] for k in ("trades", "expectancy_r", "expectancy_r_ci95", "profit_factor", "max_drawdown_pct")},
                  "| TEST", {k: v["test"][k] for k in ("trades", "expectancy_r", "expectancy_r_ci95", "profit_factor", "max_drawdown_pct")})
        print("  router", out[tf]["router"], "\n  WF router", {k: out[tf]["router_walk_forward"][k] for k in ("pooled_trades", "pooled_expectancy_r")})
    print("swap", sens)


if __name__ == "__main__":
    main()
