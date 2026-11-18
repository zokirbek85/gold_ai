"""vol_lab candidates: causality (no look-ahead) and basic behaviour on synthetic data."""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from strategy.config import RiskConfig  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402
from strategy.engine import attach_context, prepare_context, prepare_primary  # noqa: E402
from strategy.lab import default_cfg  # noqa: E402
from strategy.research import resample  # noqa: E402
from strategy import vol_lab  # noqa: E402

NOW = datetime(2026, 1, 1)


def _h1(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-03-03", periods=n * 2, freq="h")
    ts = ts[ts.weekday < 5][:n]
    close = 2000 + np.cumsum(rng.normal(0.05, 3, n))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) + rng.uniform(0.5, 3, n)
    lo = np.minimum(op, close) - rng.uniform(0.5, 3, n)
    return pd.DataFrame({"timestamp": ts, "open": op, "high": hi, "low": lo, "close": close, "volume": 0})


def _prep(df):
    h1, _ = clean_candles(df, 60, NOW)
    d1, _ = clean_candles(resample(h1, 1440), 1440, NOW)
    cfg = default_cfg(60, 1440)
    return attach_context(prepare_primary(h1, cfg), prepare_context(d1, cfg)), cfg


@pytest.mark.parametrize("name", ["squeeze_trend", "london_orb"])
def test_decisions_do_not_use_future_bars(name):
    df = _h1()
    p_full, cfg = _prep(df)
    rc = RiskConfig()
    cut = 2400
    p_cut, _ = _prep(df.iloc[:cut + 1])
    d_full = vol_lab.CANDIDATES[name][1](p_full, cfg, rc)
    d_cut = vol_lab.CANDIDATES[name][1](p_cut, cfg, rc)
    # every decision up to the cut must be identical whether or not later bars exist
    for i in range(cfg.min_history_bars, len(p_cut)):
        a, b = d_full(i), d_cut(i)
        assert (a or {}).get("action") == (b or {}).get("action"), i
        assert (a or {}).get("stop_loss") == pytest.approx((b or {}).get("stop_loss")), i


def test_london_orb_one_signal_per_day_inside_window():
    p, cfg = _prep(_h1())
    d = vol_lab.london_orb(p, cfg, RiskConfig())
    hits = [i for i in range(len(p)) if (d(i) or {}).get("action") in ("BUY", "SELL")]
    days = pd.to_datetime(p.loc[hits, "timestamp"]).dt.date
    assert len(days) == len(set(days))
    hours = pd.to_datetime(p.loc[hits, "timestamp"]).dt.hour
    assert hours.between(8, 11).all()


def test_squeeze_trend_only_with_d1_trend():
    p, cfg = _prep(_h1())
    d = vol_lab.squeeze_trend(p, cfg, RiskConfig())
    for i in range(len(p)):
        a = (d(i) or {}).get("action")
        if a == "BUY":
            assert p["c_trend"].iloc[i] == "UP"
        elif a == "SELL":
            assert p["c_trend"].iloc[i] == "DOWN"
