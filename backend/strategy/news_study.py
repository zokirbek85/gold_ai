"""
Event study: XAU/USD around US macro releases (NFP, CPI, FOMC statement).

Inputs
  events.csv  kind,date,release_utc,source   (dates parsed from bls.gov / federalreserve.gov)
  m1/<kind>_<date>.csv   Twelvedata XAU/USD 1-min bars, release −120 … +240 min
Limits (stated, not hidden)
  * no consensus forecasts → "surprise" cannot be computed; results are
    unconditional on the surprise direction;
  * no historical spread data → news-time spread is an ASSUMPTION (3× normal);
  * Twelvedata M1 is an aggregated feed, not the user's broker.

Pre-declared rules tested with costs (no parameter search):
  FOLLOW  at release+5 min enter in the direction of the first 5-min move, exit at +60
  FADE    same entry time, opposite direction, exit at +60
  BLACKOUT  v2 H4 trades with an event within ±30 min of entry vs. the rest

Usage:
    python -m strategy.news_study --events events.csv --m1 m1/ --h4 td_4h.csv --now ... --out news.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HORIZONS = [1, 5, 15, 30, 60, 120, 240]
NEWS_SPREAD = 0.90      # assumption: 3 × normal $0.30
NEWS_SLIPPAGE = 0.30    # per fill, assumption


def _ci(x, seed=7):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return [None, None]
    b = np.random.default_rng(seed).choice(x, size=(4000, len(x))).mean(axis=1)
    return [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]


def event_rows(events: pd.DataFrame, m1_dir: str):
    rows = []
    for ev in events.itertuples():
        f = os.path.join(m1_dir, f"{ev.kind}_{ev.date}.csv")
        if not os.path.exists(f):
            continue
        b = pd.read_csv(f, parse_dates=["timestamp"])
        if len(b) < 200:
            rows.append({"kind": ev.kind, "date": ev.date, "status": "no_data"})
            continue
        t0 = pd.Timestamp(ev.release_utc)
        b = b.set_index("timestamp").sort_index()
        pre = b[(b.index >= t0 - pd.Timedelta(minutes=120)) & (b.index < t0)]
        if len(pre) < 60 or (t0 - pd.Timedelta(minutes=1)) not in b.index:
            rows.append({"kind": ev.kind, "date": ev.date, "status": "missing_pre"})
            continue
        p0 = float(b.loc[t0 - pd.Timedelta(minutes=1), "close"])  # last price known BEFORE the release
        r = {"kind": ev.kind, "date": ev.date, "status": "ok", "p0": p0,
             "pre_drift_120": float(p0 - pre["open"].iloc[0]),
             "pre_range_1m": float((pre["high"] - pre["low"]).tail(60).mean())}
        for h in HORIZONS:
            key = t0 + pd.Timedelta(minutes=h - 1)
            prior = b.index[b.index <= key]
            # nearest earlier bar, at most 10 min old (the 21–22 UTC maintenance break has no bars)
            ok_bar = len(prior) and key - prior[-1] <= pd.Timedelta(minutes=10)
            r[f"r{h}"] = float(b.loc[prior[-1], "close"] - p0) if ok_bar else np.nan
        post = b[(b.index >= t0) & (b.index < t0 + pd.Timedelta(minutes=15))]
        r["post_range_1m"] = float((post["high"] - post["low"]).mean()) if len(post) else np.nan
        r["max_1m_move_first5"] = float((post.head(5)["high"] - post.head(5)["low"]).max()) if len(post) else np.nan
        e5, e60 = t0 + pd.Timedelta(minutes=5), t0 + pd.Timedelta(minutes=60)
        if e5 in b.index and e60 in b.index:
            r["entry5"], r["exit60"] = float(b.loc[e5, "open"]), float(b.loc[e60, "open"])
        rows.append(r)
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame, split: str):
    ok = df[df["status"] == "ok"].copy()
    out = {"events_total": int(len(df)), "events_with_data": int(len(ok)),
           "no_data": df[df["status"] != "ok"][["kind", "date", "status"]].to_dict("records")}
    per = {}
    for kind, g in ok.groupby("kind"):
        k = {"n": int(len(g))}
        for h in HORIZONS:
            x = g[f"r{h}"].dropna()
            k[f"+{h}m"] = {"mean_usd": round(float(x.mean()), 2), "median_usd": round(float(x.median()), 2),
                           "mean_abs_usd": round(float(x.abs().mean()), 2), "up_share": round(float((x > 0).mean()), 3),
                           "mean_ci95": _ci(x)}
        k["range_expansion_x"] = round(float((g["post_range_1m"] / g["pre_range_1m"]).median()), 2)
        k["median_max_1m_range_first5_usd"] = round(float(g["max_1m_move_first5"].median()), 2)
        x5, x60 = g["r5"], g["r60"] - g["r5"]
        m = x5.notna() & x60.notna() & (x5 != 0)
        k["impulse_continuation_share"] = round(float((np.sign(x5[m]) == np.sign(x60[m])).mean()), 3)
        k["impulse_vs_later_corr"] = round(float(np.corrcoef(x5[m], x60[m])[0, 1]), 3) if m.sum() > 3 else None
        k["by_year_r60_mean"] = {str(y): round(float(v), 2) for y, v in g.groupby(g["date"].str[:4])["r60"].mean().items()}
        per[kind] = k
    out["by_event"] = per

    # pre-declared FOLLOW / FADE with news-time costs (USD/oz)
    t = ok.dropna(subset=["entry5", "exit60", "r5"])
    t = t[t["r5"] != 0]
    cost = NEWS_SPREAD + 2 * NEWS_SLIPPAGE
    move = t["exit60"] - t["entry5"]
    follow = np.sign(t["r5"]) * move - cost
    fade = -np.sign(t["r5"]) * move - cost
    rules = {}
    for name, pnl in (("FOLLOW", follow), ("FADE", fade)):
        res = {}
        for part, mask in (("train", t["date"] < split), ("test", t["date"] >= split), ("all", t["date"] == t["date"])):
            x = pnl[mask]
            res[part] = {"n": int(len(x)), "mean_net_usd_per_oz": round(float(x.mean()), 2) if len(x) else None,
                         "win_rate": round(float((x > 0).mean() * 100), 1) if len(x) else None,
                         "ci95": _ci(x), "gross_mean_usd": round(float((x + cost).mean()), 2) if len(x) else None}
        rules[name] = res
    out["rules"] = {"assumed_cost_usd_per_oz": cost, "results": rules}
    return out


def blackout_test(events: pd.DataFrame, h4_csv: str, now: datetime):
    """v2 H4 trades: entry within ±30 min of a release vs. the rest (2022-01 onward)."""
    from strategy.backtest import metrics, simulate, v2_decider
    from strategy.config import RiskConfig
    from strategy.data_quality import clean_candles
    from strategy.engine import attach_context, prepare_context, prepare_primary
    from strategy.lab import default_cfg
    from strategy.research import resample
    h4, _ = clean_candles(pd.read_csv(h4_csv), 240, now)
    d1, _ = clean_candles(resample(h4, 1440), 1440, now)
    cfg, rc = default_cfg(240, 1440), RiskConfig()
    p = attach_context(prepare_primary(h4, cfg), prepare_context(d1, cfg))
    start = int((p["timestamp"] < pd.Timestamp("2022-01-01")).sum())
    trades = simulate(p, v2_decider(p, cfg, rc), rc, cfg.max_hold_bars, start)["trades"]
    rel = pd.to_datetime(events["release_utc"]).sort_values().to_numpy()

    def near(ts, minutes):
        t = np.datetime64(pd.Timestamp(ts))
        return bool((np.abs(rel - t) <= np.timedelta64(minutes, "m")).any())

    def during_first(ts, hours):
        t = np.datetime64(pd.Timestamp(ts))
        return bool(((rel >= t) & (rel <= t + np.timedelta64(hours, "h"))).any())
    a = [x for x in trades if near(x.entry_time, 30)]
    b = [x for x in trades if not near(x.entry_time, 30)]
    c = [x for x in trades if during_first(x.entry_time, 24)]
    d = [x for x in trades if not during_first(x.entry_time, 24)]
    k = ("trades", "expectancy_r", "expectancy_r_ci95", "win_rate")
    f = lambda tr: {x: metrics(tr).get(x) for x in k}  # noqa: E731
    return {"all": f(trades), "entry_within_30m_of_event": f(a), "other": f(b),
            "event_within_24h_after_entry": f(c), "no_event_within_24h": f(d)}


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--m1", required=True)
    ap.add_argument("--h4", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--split", default="2024-07-01")
    ap.add_argument("--out", default="news_study.json")
    a = ap.parse_args()
    ev = pd.read_csv(a.events)
    df = event_rows(ev, a.m1)
    out = {"generated_at": datetime.utcnow().isoformat() + "Z", "sources": sorted(ev["source"].unique().tolist()),
           "assumptions": {"news_spread_usd": NEWS_SPREAD, "news_slippage_usd": NEWS_SLIPPAGE,
                           "price_feed": "Twelvedata XAU/USD 1min (aggregated, not broker)"},
           **summarise(df, a.split), "v2_blackout": blackout_test(ev, a.h4, datetime.fromisoformat(a.now))}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps({k: out[k] for k in ("events_total", "events_with_data", "rules", "v2_blackout")}, indent=1, default=str))
    for kind, v in out["by_event"].items():
        print(kind, v["n"], {h: (v[h]["mean_abs_usd"], v[h]["mean_usd"], v[h]["up_share"]) for h in ("+5m", "+60m", "+240m")},
              "expansion", v["range_expansion_x"], "cont", v["impulse_continuation_share"], "corr", v["impulse_vs_later_corr"])


if __name__ == "__main__":
    main()
