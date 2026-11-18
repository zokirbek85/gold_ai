"""cross_lab: range_fade causality / D1 gating, price scaling invariance of R."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from strategy.config import RiskConfig  # noqa: E402
from strategy import cross_lab  # noqa: E402
from test_vol_lab import _h1, _prep  # noqa: E402


def test_range_fade_no_lookahead_and_only_without_d1_trend():
    df = _h1(seed=3)
    p_full, cfg = _prep(df)
    cut = 2400
    p_cut, _ = _prep(df.iloc[:cut + 1])
    rc = RiskConfig()
    d_full, d_cut = cross_lab.range_fade(p_full, cfg, rc), cross_lab.range_fade(p_cut, cfg, rc)
    for i in range(cfg.min_history_bars, len(p_cut)):
        a, b = d_full(i) or {}, d_cut(i) or {}
        assert a.get("action") == b.get("action"), i
        if a.get("action") in ("BUY", "SELL"):
            assert p_full["c_trend"].iloc[i] == "NONE"


def test_r_multiples_are_scale_invariant():
    """Scaling prices and costs together must not change R (justifies the FX price scaling)."""
    from strategy.backtest import simulate
    df = _h1(seed=5)
    p1, cfg = _prep(df)
    scaled = df.copy()
    for k in ("open", "high", "low", "close"):
        scaled[k] = scaled[k] * 100
    p2, _ = _prep(scaled)
    rc1 = RiskConfig(spread=0.3, slippage=0.1, max_spread=0.6)
    rc2 = RiskConfig(spread=30.0, slippage=10.0, max_spread=60.0)
    t1 = simulate(p1, cross_lab.control(p1, cfg, rc1, 0.05, 1, "none"), rc1, cfg.max_hold_bars, cfg.min_history_bars)["trades"]
    t2 = simulate(p2, cross_lab.control(p2, cfg, rc2, 0.05, 1, "none"), rc2, cfg.max_hold_bars, cfg.min_history_bars)["trades"]
    assert len(t1) >= 5 and len(t1) == len(t2)
    assert np.allclose([t.r for t in t1], [t.r for t in t2], atol=2e-3)
