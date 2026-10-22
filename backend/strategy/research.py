"""
Reproducible research run: legacy engine vs v2, train/test split, walk-forward.

Usage (from repo root, needs H1 and H4 CSVs with timestamp,open,high,low,close,volume):
    ML_MODEL_DIR=/tmp/empty python -m strategy.research \
        --h1 data/td_1h.csv --h4 data/td_4h.csv --split 2025-04-01 --out results.json

Rules:
  * parameters are chosen on the TRAIN period only (expectancy, ≥ 40 trades);
  * the TEST period is evaluated once for the chosen variant, and for every grid
    variant only to show robustness (not to pick);
  * the legacy engine runs on identical clean data and the same execution model.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import warnings
from dataclasses import asdict, replace
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import STRATEGY_VERSION  # noqa: E402
from strategy.backtest import breakdown, metrics, simulate, v2_decider  # noqa: E402
from strategy.config import RiskConfig, StrategyConfig  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402
from strategy.engine import attach_context, prepare_context, prepare_primary  # noqa: E402

GRID = {
    "target_rr": [2.0, 2.5, 3.0],
    "min_room_r": [0.0, 1.0],
    "context_mode": ["strict", "not_against"],
    "enable_range_setup": [False, True],
}
MIN_TRAIN_TRADES = 40


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate clean candles to a higher timeframe (bars labelled by OPEN time, UTC)."""
    x = df.set_index("timestamp")
    agg = x.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return agg.reset_index()


def legacy_decider(p: pd.DataFrame, window: int = 300):
    """Adapter around services.signal_service.generate_signal (news/econ neutral, no ML model)."""
    from services.signal_service import generate_signal
    recs = p[["timestamp", "open", "high", "low", "close", "volume"]].to_dict("records")

    def decide(i: int):
        if i < 50:
            return None
        s = generate_signal(recs[max(0, i - window + 1): i + 1])
        if s["signal_type"] not in ("BUY", "SELL") or not s.get("stop_loss") or not s.get("take_profit"):
            return {"action": "NO TRADE", "reason_codes": ["LEGACY_NEUTRAL"]}
        return {"action": s["signal_type"], "entry": s["entry"], "stop_loss": s["stop_loss"],
                "take_profit": s["take_profit"], "regime": "n/a", "signal_score": s.get("confidence")}
    return decide


def random_controls(p, cfg, rc, start, end, v2_expectancy, runs=200, prob=0.02):
    """Random entries with the same execution/costs (SL 1.5·ATR, TP target_rr·risk).

    Answers: does the setup beat drift? 'long_ctx_up' = random longs only while
    the context trend is UP; 'both' = random direction.
    """
    import random
    import numpy as np
    c, a, trend = p["close"].to_numpy(), p["atr"].to_numpy(), p["c_trend"].to_numpy()

    def make(mode, seed):
        rnd = random.Random(seed)

        def d(i):
            if rnd.random() > prob or not np.isfinite(a[i]):
                return None
            if mode == "long_ctx_up" and trend[i] != "UP":
                return None
            side = rnd.choice(["BUY", "SELL"]) if mode == "both" else "BUY"
            s, risk = (1 if side == "BUY" else -1), 1.5 * a[i]
            return {"action": side, "entry": c[i], "stop_loss": c[i] - s * risk,
                    "take_profit": c[i] + s * cfg.target_rr * risk, "regime": "random"}
        return d

    out = {}
    for mode in ("long", "long_ctx_up", "both"):
        e = []
        for seed in range(runs):
            m = metrics(simulate(p, make(mode, seed), rc, cfg.max_hold_bars, start, end)["trades"])
            if m.get("trades"):
                e.append(m["expectancy_r"])
        e = np.array(e)
        out[mode] = {"runs": len(e), "mean_expectancy_r": round(float(e.mean()), 3),
                     "p95": round(float(np.percentile(e, 95)), 3),
                     "share_ge_v2": round(float((e >= v2_expectancy).mean()), 3)}
    return out


def _index_at(p: pd.DataFrame, ts: str) -> int:
    return int((p["timestamp"] < pd.Timestamp(ts)).sum())


def _run(p, decide, rc, cfg, start, end):
    res = simulate(p, decide, rc, cfg.max_hold_bars, start, end)
    m = metrics(res["trades"], rc.risk_pct)
    return res, m


def main() -> None:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True, help="primary timeframe CSV")
    ap.add_argument("--h4", default=None, help="context timeframe CSV (omit → resample primary)")
    ap.add_argument("--primary-tf", type=int, default=60)
    ap.add_argument("--context-tf", type=int, default=240)
    ap.add_argument("--skip-legacy", action="store_true")
    ap.add_argument("--split", default="2025-04-01")
    ap.add_argument("--now", default=None, help="UTC time the data was fetched (drops forming bars)")
    ap.add_argument("--out", default="research_results.json")
    args = ap.parse_args()

    now = datetime.fromisoformat(args.now) if args.now else datetime.utcnow()
    h1, q1 = clean_candles(pd.read_csv(args.h1), args.primary_tf, now)
    if args.h4:
        h4, q4 = clean_candles(pd.read_csv(args.h4), args.context_tf, now)
    else:
        h4, q4 = clean_candles(resample(h1, args.context_tf), args.context_tf, now)
    base_cfg = replace(StrategyConfig(), primary_tf=args.primary_tf, context_tf=args.context_tf)
    rc = RiskConfig()
    ctx = prepare_context(h4, base_cfg)
    p = attach_context(prepare_primary(h1, base_cfg), ctx)

    warm = base_cfg.min_history_bars
    split = _index_at(p, args.split)
    n = len(p)
    out = {
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data": {"h1": q1.to_dict(), "h4": q4.to_dict(),
                 "train": [str(p["timestamp"].iloc[warm]), str(p["timestamp"].iloc[split - 1])],
                 "test": [str(p["timestamp"].iloc[split]), str(p["timestamp"].iloc[-1])]},
        "risk_config": asdict(rc),
    }

    # ── Legacy baseline ─────────────────────────────────────────────────────
    out["legacy"] = {}
    legacy_runs = {} if args.skip_legacy else {"train": (warm, split), "test": (split, n)}
    leg = legacy_decider(p)
    for name, (a, b) in legacy_runs.items():
        res, m = _run(p, leg, rc, base_cfg, a, b)
        out["legacy"][name] = {"metrics": m, "signals": res["signals"], "skipped": res["skipped"],
                               "by_direction": breakdown(res["trades"], lambda t: t.direction, rc.risk_pct)}
    # legacy without costs, to show what the old /backtesting/run ignored
    if legacy_runs:
        free = replace(rc, spread=0.0, slippage=0.0)
        _, m_free = _run(p, leg, free, base_cfg, split, n)
        out["legacy"]["test_zero_cost"] = m_free

    # ── v2 grid on TRAIN ────────────────────────────────────────────────────
    keys = list(GRID)
    grid = []
    for combo in itertools.product(*(GRID[k] for k in keys)):
        cfg = replace(base_cfg, **dict(zip(keys, combo)))
        _, m_tr = _run(p, v2_decider(p, cfg, rc), rc, cfg, warm, split)
        _, m_te = _run(p, v2_decider(p, cfg, rc), rc, cfg, split, n)
        grid.append({"params": dict(zip(keys, combo)), "train": m_tr, "test": m_te})
    eligible = [g for g in grid if g["train"].get("trades", 0) >= MIN_TRAIN_TRADES]
    chosen = max(eligible, key=lambda g: g["train"]["expectancy_r"]) if eligible else None
    out["grid"] = [{"params": g["params"],
                    "train": {k: g["train"].get(k) for k in ("trades", "win_rate", "profit_factor", "expectancy_r")},
                    "test": {k: g["test"].get(k) for k in ("trades", "win_rate", "profit_factor", "expectancy_r")}}
                   for g in grid]
    out["grid_test_positive_share"] = round(
        sum(1 for g in grid if (g["test"].get("expectancy_r") or -1) > 0) / len(grid), 3)

    if chosen:
        cfg = replace(base_cfg, **chosen["params"])
        dec = v2_decider(p, cfg, rc)
        res_tr, m_tr = _run(p, dec, rc, cfg, warm, split)
        res_te, m_te = _run(p, dec, rc, cfg, split, n)
        tr = res_te["trades"]
        out["v2"] = {
            "chosen_params": chosen["params"],
            "config_hash": cfg.version_hash(),
            "train": {"metrics": m_tr, "signals": res_tr["signals"]},
            "test": {"metrics": m_te, "signals": res_te["signals"], "skipped": res_te["skipped"],
                     "no_trade_codes": res_te["no_trade_codes"],
                     "by_regime": breakdown(tr, lambda t: t.regime, rc.risk_pct),
                     "by_direction": breakdown(tr, lambda t: t.direction, rc.risk_pct),
                     "by_half_year": breakdown(tr, lambda t: t.entry_time[:4] + ("H1" if t.entry_time[5:7] <= "06" else "H2"), rc.risk_pct),
                     "by_score": breakdown(tr, lambda t: "score<60" if (t.score or 0) < 60 else "score≥60", rc.risk_pct)},
        }
        # cost sensitivity on TEST
        sens = {}
        for sp in (0.2, 0.3, 0.5, 0.8):
            rc2 = replace(rc, spread=sp)
            _, m = _run(p, v2_decider(p, cfg, rc2), rc2, cfg, split, n)
            sens[f"spread_{sp}"] = {k: m.get(k) for k in ("trades", "expectancy_r", "profit_factor")}
        out["v2"]["test_spread_sensitivity"] = sens
        out["v2"]["random_controls"] = {
            "train": random_controls(p, cfg, rc, warm, split, m_tr.get("expectancy_r") or 0),
            "test": random_controls(p, cfg, rc, split, n, m_te.get("expectancy_r") or 0),
        }

        # walk-forward: re-select on each 12-month window, evaluate next 6 months
        wf = []
        starts = pd.date_range(p["timestamp"].iloc[warm].normalize(), p["timestamp"].iloc[-1], freq="6MS")
        for s in starts:
            tr_a, tr_b = s, s + pd.DateOffset(months=12)
            te_b = tr_b + pd.DateOffset(months=6)
            ia, ib, ic = _index_at(p, str(tr_a)), _index_at(p, str(tr_b)), _index_at(p, str(te_b))
            if ib >= n or ic - ib < 200:
                continue
            best, best_e = None, None
            for g in grid:
                c2 = replace(base_cfg, **g["params"])
                _, m = _run(p, v2_decider(p, c2, rc), rc, c2, max(ia, warm), ib)
                if m.get("trades", 0) >= 20 and (best_e is None or m["expectancy_r"] > best_e):
                    best, best_e = g["params"], m["expectancy_r"]
            if best is None:
                wf.append({"train": [str(tr_a.date()), str(tr_b.date())], "note": "no eligible variant"})
                continue
            c2 = replace(base_cfg, **best)
            res, m = _run(p, v2_decider(p, c2, rc), rc, c2, ib, ic)
            wf.append({"train": [str(tr_a.date()), str(tr_b.date())], "test_until": str(te_b.date()),
                       "params": best, "train_expectancy_r": best_e,
                       "oos": {k: m.get(k) for k in ("trades", "win_rate", "profit_factor", "expectancy_r", "max_drawdown_r")},
                       "_trades": [t.r for t in res["trades"]]})
        all_oos = [r for w in wf for r in w.pop("_trades", [])]
        out["walk_forward"] = {"windows": wf, "pooled_oos_trades": len(all_oos),
                               "pooled_oos_expectancy_r": round(sum(all_oos) / len(all_oos), 3) if all_oos else None}
    else:
        out["v2"] = {"note": f"No grid variant reached {MIN_TRAIN_TRADES} trades in train"}

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps({"legacy_test": out["legacy"].get("test", {}).get("metrics"),
                      "v2_chosen": out["v2"].get("chosen_params"),
                      "v2_train": out["v2"].get("train", {}).get("metrics"),
                      "v2_test": out["v2"].get("test", {}).get("metrics"),
                      "grid_test_positive_share": out["grid_test_positive_share"],
                      "walk_forward": out.get("walk_forward", {}).get("pooled_oos_expectancy_r")}, indent=1, default=str))


if __name__ == "__main__":
    main()
