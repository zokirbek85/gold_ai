"""Tests for the v2 strategy package (backend/strategy) and the audit bug fixes."""
import json
import math
import os
import random
import sys
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from strategy import indicators as ind  # noqa: E402
from strategy.backtest import metrics, simulate  # noqa: E402
from strategy.config import RiskConfig, StrategyConfig  # noqa: E402
from strategy.data_quality import (  # noqa: E402
    MARKET_CLOSED, OK, STALE, INSUFFICIENT, assess, clean_candles, is_market_closed,
)
from strategy.engine import (  # noqa: E402
    BUY, HIGH_VOL, NO_TRADE, SELL, attach_context, classify_regime, evaluate_bar,
    prepare_context, prepare_primary,
)
from strategy.live import generate, legacy_view, position_size  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _walk(n, start=datetime(2026, 1, 5, 0), tf=60, seed=1, drift=0.0, vol=3.0, price=4000.0):
    """Random-walk candles on weekdays only (Mon 00:00 start)."""
    rnd = random.Random(seed)
    rows, t = [], start
    while len(rows) < n:
        if not is_market_closed(t):
            o = price
            c = o + drift + rnd.gauss(0, vol)
            rows.append({"timestamp": t, "open": o, "high": max(o, c) + rnd.uniform(0.2, 2),
                         "low": min(o, c) - rnd.uniform(0.2, 2), "close": c, "volume": 0})
            price = c
        t += timedelta(minutes=tf)
    return rows


def _frame(n=12, **over):
    """A prepared primary frame with hand-set indicator values (full control of rules)."""
    t0 = pd.Timestamp("2026-03-02 00:00")
    rows = []
    for k in range(n):
        rows.append({
            "timestamp": t0 + pd.Timedelta(hours=4 * k), "open": 4000.0, "high": 4004.0,
            "low": 3996.0, "close": 4000.0, "volume": 0.0,
            "ema_fast": 3999.0, "ema_slow": 3990.0, "atr": 10.0, "atr_med": 10.0,
            "adx": 30.0, "rsi": 55.0, "c_trend": "UP", "c_close": 4000.0, "c_ema_trend": 3800.0,
        })
    df = pd.DataFrame(rows)
    df["close_time"] = df["timestamp"] + pd.Timedelta(minutes=240)
    for k, v in over.items():
        df[k] = v
    return df


def _buy_setup(df):
    """Pullback to EMA20 then a bullish trigger bar closing above the previous high."""
    i = len(df) - 1
    df.loc[i - 2, ["open", "high", "low", "close"]] = [4002.0, 4003.0, 3995.0, 3998.0]  # pullback touches EMA20
    df.loc[i - 1, ["open", "high", "low", "close"]] = [3998.0, 4001.0, 3994.0, 3999.0]
    df.loc[i, ["open", "high", "low", "close"]] = [3999.0, 4008.0, 3998.0, 4007.0]      # trigger
    return df


def _sell_setup(df):
    i = len(df) - 1
    df["ema_fast"], df["ema_slow"], df["c_trend"], df["c_close"], df["c_ema_trend"] = 4001.0, 4010.0, "DOWN", 4000.0, 4200.0
    df["rsi"] = 45.0
    df.loc[i - 2, ["open", "high", "low", "close"]] = [3998.0, 4005.0, 3997.0, 4002.0]
    df.loc[i - 1, ["open", "high", "low", "close"]] = [4002.0, 4006.0, 3999.0, 4001.0]
    df.loc[i, ["open", "high", "low", "close"]] = [4001.0, 4002.0, 3992.0, 3993.0]
    return df


CFG = StrategyConfig()
RC = RiskConfig()


# ── indicators ───────────────────────────────────────────────────────────────

class TestIndicators:
    def test_match_legacy_scalar_implementations(self):
        from services.indicator_service import _ema, _rsi, _atr
        c = _walk(300)
        closes = np.array([x["close"] for x in c])
        h = np.array([x["high"] for x in c]); l = np.array([x["low"] for x in c])
        assert ind.ema(closes, 20)[-1] == pytest.approx(_ema(list(closes), 20))
        assert ind.rsi(closes, 14)[-1] == pytest.approx(_rsi(list(closes), 14))
        assert ind.atr(h, l, closes, 14)[-1] == pytest.approx(_atr(c, 14))

    def test_adx_bounded_and_trend_sensitive(self):
        trend = _walk(300, drift=2.0, vol=1.0)
        noise = _walk(300, drift=0.0, vol=3.0, seed=7)
        def last_adx(c):
            a = ind.adx(*(np.array([x[k] for x in c]) for k in ("high", "low", "close")))
            return a[-1]
        t, r = last_adx(trend), last_adx(noise)
        assert 0 <= r <= 100 and 0 <= t <= 100
        assert t > 40 and t > r

    def test_indicators_are_causal(self):
        c = _walk(400)
        full = prepare_primary(pd.DataFrame(c), CFG)
        cut = prepare_primary(pd.DataFrame(c[:300]), CFG)
        cols = ["ema_fast", "ema_slow", "atr", "atr_med", "adx", "rsi"]
        np.testing.assert_allclose(full.loc[:299, cols].to_numpy(), cut[cols].to_numpy(), equal_nan=True)

    def test_nan_until_enough_history(self):
        assert np.isnan(ind.ema(np.arange(10.0), 20)).all()
        assert np.isnan(ind.adx(np.ones(10), np.ones(10), np.ones(10))).all()


class TestLegacyRegimeAdxFix:
    def test_core_regime_adx_in_range(self):
        from core.regime import MarketRegimeDetector
        adx = MarketRegimeDetector()._adx(_walk(200, drift=1.0))
        assert 0 <= adx <= 100

    def test_core_regime_matches_strategy_adx(self):
        from core.regime import MarketRegimeDetector
        c = _walk(200, drift=1.0)
        ref = ind.adx(*(np.array([x[k] for x in c]) for k in ("high", "low", "close")))[-1]
        assert MarketRegimeDetector()._adx(c) == pytest.approx(ref, abs=0.2)


# ── data quality ─────────────────────────────────────────────────────────────

class TestDataQuality:
    def test_forming_bar_dropped(self):
        c = _walk(10, start=datetime(2026, 3, 2, 0))
        now = c[-1]["timestamp"] + timedelta(minutes=30)  # last bar still open
        df, rep = clean_candles(c, 60, now)
        assert rep.dropped_forming == 1 and len(df) == 9

    def test_weekend_filler_dropped(self):
        c = _walk(50, start=datetime(2026, 3, 2, 0))
        sat = datetime(2026, 3, 7, 10)
        c.append({"timestamp": sat, "open": 4000, "high": 4000.2, "low": 3999.9, "close": 4000.1, "volume": 0})
        df, rep = clean_candles(c, 60, datetime(2026, 3, 9))
        assert rep.dropped_weekend >= 1 and sat not in set(df["timestamp"])

    def test_foreign_series_dropped(self):
        c = _walk(100, start=datetime(2026, 3, 2, 0))
        bad = [dict(x, timestamp=x["timestamp"] + timedelta(minutes=30), open=2300.0, high=2305.0,
                    low=2295.0, close=2301.0, volume=900) for x in c[10:20]]
        df, rep = clean_candles(c + bad, 60, datetime(2026, 4, 1))
        assert rep.dropped_foreign == 10
        assert df["close"].min() > 3000

    def test_duplicates_unsorted_invalid(self):
        c = _walk(30, start=datetime(2026, 3, 2, 0))
        dup = dict(c[5]); bad = dict(c[6], high=c[6]["low"] - 1)
        nan = dict(c[7], close=float("nan"))
        rows = list(reversed(c)) + [dup, bad, nan]
        df, rep = clean_candles(rows, 60, datetime(2026, 4, 1))
        assert df["timestamp"].is_monotonic_increasing and df["timestamp"].is_unique
        assert rep.dropped_invalid == 2 and rep.dropped_duplicates >= 1

    def test_stale_and_insufficient_and_closed(self):
        c = _walk(300, start=datetime(2026, 3, 2, 0))
        last_close = c[-1]["timestamp"] + timedelta(hours=1)
        _, rep = clean_candles(c, 60, last_close + timedelta(minutes=10))
        assert assess(rep, last_close + timedelta(minutes=10), 250, 1.5, 3).status == OK
        _, rep = clean_candles(c, 60, last_close + timedelta(hours=5))
        now = last_close + timedelta(hours=5)
        if not is_market_closed(now):
            assert assess(rep, now, 250, 1.5, 3).status == STALE
        _, rep = clean_candles(c[:100], 60, last_close)
        assert assess(rep, last_close, 250, 1.5, 3).status == INSUFFICIENT
        _, rep = clean_candles(c, 60, datetime(2026, 3, 28, 12))  # Saturday
        assert assess(rep, datetime(2026, 3, 28, 12), 250, 1.5, 3).status == MARKET_CLOSED

    def test_empty(self):
        df, rep = clean_candles([], 60)
        assert rep.status == INSUFFICIENT and df.empty


# ── decision rules ───────────────────────────────────────────────────────────

class TestRules:
    def test_buy_signal_levels(self):
        df = _buy_setup(_frame())
        d = evaluate_bar(df, len(df) - 1, CFG, RC)
        assert d.action == BUY, d.reason_codes
        assert d.stop_loss < d.entry < d.tp1 < d.take_profit
        risk = d.entry - d.stop_loss
        assert d.take_profit - d.entry == pytest.approx(CFG.target_rr * risk, abs=0.02)
        assert risk >= CFG.sl_min_atr * 10.0 - 1e-6
        assert d.rr_net >= CFG.min_rr
        assert 0 <= d.signal_score <= 100 and set(d.score_components) >= {"htf_alignment", "trend_strength"}
        assert d.expires_at and d.invalidation

    def test_sell_signal_levels(self):
        df = _sell_setup(_frame())
        df["adx"] = 30.0
        d = evaluate_bar(df, len(df) - 1, CFG, RC)
        assert d.action == SELL, d.reason_codes
        assert d.take_profit < d.tp1 < d.entry < d.stop_loss
        assert d.entry - d.take_profit == pytest.approx(CFG.target_rr * (d.stop_loss - d.entry), abs=0.02)

    @pytest.mark.parametrize("over,code", [
        ({"atr": 25.0}, "VOLATILITY_TOO_HIGH"),
        ({"atr": 4.0}, "VOLATILITY_TOO_LOW"),
        ({"c_trend": "NONE"}, "HTF_CONFLICT"),
        ({"c_trend": "DOWN"}, "HTF_CONFLICT"),
        ({"adx": 20.0}, "TRANSITION"),
        ({"adx": 15.0}, "RANGE_DISABLED"),
        ({"rsi": 75.0}, "RSI_OVERBOUGHT"),
    ])
    def test_no_trade_conditions(self, over, code):
        df = _buy_setup(_frame())
        for k, v in over.items():
            df[k] = v
        d = evaluate_bar(df, len(df) - 1, CFG, RC)
        assert d.action == NO_TRADE and code in d.reason_codes

    def test_no_trigger(self):
        df = _buy_setup(_frame())
        i = len(df) - 1
        df.loc[i, ["open", "close"]] = [4006.0, 4000.0]  # bearish bar
        d = evaluate_bar(df, i, CFG, RC)
        assert d.action == NO_TRADE and "NO_TRIGGER" in d.reason_codes

    def test_spread_filters(self):
        df = _buy_setup(_frame())
        i = len(df) - 1
        assert "SPREAD_TOO_HIGH" in evaluate_bar(df, i, CFG, RC, spread=1.0).reason_codes
        tight = replace(RC, max_spread_to_risk=0.01)
        assert "SPREAD_TOO_HIGH_VS_SL" in evaluate_bar(df, i, CFG, tight, spread=0.5).reason_codes

    def test_sl_too_wide(self):
        df = _buy_setup(_frame())
        i = len(df) - 1
        df.loc[i - 1, "low"] = 3960.0  # swing 4 ATR below
        d = evaluate_bar(df, i, CFG, RC)
        assert d.action == NO_TRADE and "SL_TOO_WIDE" in d.reason_codes

    def test_rr_after_costs(self):
        df = _buy_setup(_frame())
        d = evaluate_bar(df, len(df) - 1, replace(CFG, target_rr=1.5, min_rr=1.5), RC)
        assert d.action == NO_TRADE and "RR_TOO_LOW" in d.reason_codes

    def test_rollover_hours(self):
        df = _buy_setup(_frame())
        i = len(df) - 1
        df.loc[i, "close_time"] = pd.Timestamp("2026-03-03 21:00")
        assert "ROLLOVER_SESSION" in evaluate_bar(df, i, CFG, RC).reason_codes

    def test_regime_labels(self):
        row = _frame().iloc[-1].copy()
        row["atr"] = 30.0
        assert classify_regime(row, CFG) == HIGH_VOL
        row["atr"] = float("nan")
        assert classify_regime(row, CFG) == "INSUFFICIENT_DATA"

    def test_context_uses_only_closed_htf_bars(self):
        p = prepare_primary(pd.DataFrame(_walk(300, tf=240, start=datetime(2025, 1, 6))), replace(CFG))
        ctx_raw = pd.DataFrame(_walk(300, tf=1440, start=datetime(2024, 6, 3)))
        ctx = prepare_context(ctx_raw, CFG)
        m = attach_context(p, ctx)
        ok = m.dropna(subset=["c_close_time"])
        assert (ok["c_close_time"] <= ok["close_time"]).all()


# ── backtest execution ───────────────────────────────────────────────────────

def _bars(rows):
    t0 = pd.Timestamp("2026-03-02 00:00")
    return pd.DataFrame([{"timestamp": t0 + pd.Timedelta(hours=4 * k), "open": o, "high": h,
                          "low": l, "close": c} for k, (o, h, l, c) in enumerate(rows)])


def _one_signal(entry=100.0, sl=90.0, tp=125.0, side=BUY):
    sent = {"done": False}
    def decide(i):
        if i == 0 and not sent["done"]:
            sent["done"] = True
            return {"action": side, "entry": entry, "stop_loss": sl, "take_profit": tp, "regime": "T"}
        return None
    return decide


ZERO = replace(RC, spread=0.0, slippage=0.0)


class TestBacktest:
    def test_tp_hit_exact_r(self):
        p = _bars([(100, 101, 99, 100), (100, 126, 99, 120), (120, 121, 119, 120)])
        t = simulate(p, _one_signal(), ZERO, 48)["trades"][0]
        assert t.exit_reason == "TP" and t.r == pytest.approx(2.5)

    def test_sl_first_when_both_touched(self):
        p = _bars([(100, 101, 99, 100), (100, 130, 85, 110), (110, 111, 109, 110)])
        t = simulate(p, _one_signal(), ZERO, 48)["trades"][0]
        assert t.exit_reason == "SL_AMBIGUOUS" and t.r == pytest.approx(-1.0)

    def test_gap_through_stop_uses_open(self):
        p = _bars([(100, 101, 99, 100), (100, 102, 95, 96), (80, 82, 78, 81)])
        t = simulate(p, _one_signal(), ZERO, 48)["trades"][0]
        assert t.exit_reason == "SL_GAP" and t.r == pytest.approx(-2.0)

    def test_time_exit(self):
        p = _bars([(100, 101, 99, 100)] + [(100, 102, 98, 101)] * 5)
        t = simulate(p, _one_signal(), ZERO, 3)["trades"][0]
        assert t.exit_reason == "TIME" and t.bars_held == 3

    def test_costs_reduce_r(self):
        rc = replace(RC, spread=0.4, slippage=0.1)
        p = _bars([(100, 101, 99, 100), (100, 126, 99, 120), (120, 121, 119, 120)])
        t = simulate(p, _one_signal(), rc, 48)["trades"][0]
        # fill 100+0.2+0.1, exit TP 125 at bid (high-0.2 ≥ 125) → pnl 24.7 → 2.47R
        assert t.r == pytest.approx(2.47, abs=1e-6)
        assert t.cost_r == pytest.approx(0.05, abs=1e-6)

    def test_sell_side_and_zone_skip(self):
        p = _bars([(100, 101, 99, 100), (100, 101, 74, 80), (80, 81, 79, 80)])
        t = simulate(p, _one_signal(100, 110, 75, SELL), ZERO, 48)["trades"][0]
        assert t.exit_reason == "TP" and t.r == pytest.approx(2.5)
        def decide(i):
            return {"action": BUY, "entry": 100, "stop_loss": 90, "take_profit": 125,
                    "entry_zone": {"low": 99, "high": 101}} if i == 0 else None
        p2 = _bars([(100, 101, 99, 100), (105, 106, 104, 105), (105, 106, 104, 105)])
        res = simulate(p2, decide, ZERO, 48)
        assert not res["trades"] and res["skipped"]["ENTRY_ZONE_MISSED"] == 1

    def test_metrics_math(self):
        class T:  # minimal trade stub
            def __init__(self, r): self.r, self.cost_r, self.exit_reason, self.bars_held = r, 0.0, "x", 1
        m = metrics([T(2.0), T(-1.0), T(-1.0), T(2.0), T(-1.0)], risk_pct=1.0)
        assert m["win_rate"] == 40.0
        assert m["profit_factor"] == pytest.approx(4 / 3, abs=0.01)
        assert m["expectancy_r"] == pytest.approx(0.2)
        assert m["max_drawdown_r"] == pytest.approx(2.0)
        assert m["max_consecutive_losses"] == 2

    def test_deterministic_and_no_lookahead(self):
        cfg = replace(CFG, primary_tf=60, context_tf=240)
        h1 = pd.DataFrame(_walk(1500, drift=0.15, seed=3))
        ctx = pd.DataFrame(_walk(600, tf=240, drift=0.6, seed=4, start=datetime(2025, 10, 6)))
        p = attach_context(prepare_primary(h1, cfg), prepare_context(ctx, cfg))
        from strategy.backtest import v2_decider
        a = simulate(p, v2_decider(p, cfg, RC), RC, cfg.max_hold_bars, 300)
        b = simulate(p, v2_decider(p, cfg, RC), RC, cfg.max_hold_bars, 300)
        assert [t.__dict__ for t in a["trades"]] == [t.__dict__ for t in b["trades"]]
        # decisions on bar i must not change when future bars are removed
        for i in range(400, 1400, 97):
            cut = attach_context(prepare_primary(h1.iloc[:i + 1], cfg), prepare_context(ctx, cfg))
            full_d, cut_d = evaluate_bar(p, i, cfg, RC), evaluate_bar(cut, i, cfg, RC)
            assert (full_d.action, full_d.stop_loss, full_d.reason_codes) == \
                   (cut_d.action, cut_d.stop_loss, cut_d.reason_codes)


# ── risk / live ──────────────────────────────────────────────────────────────

class TestRiskAndLive:
    def test_position_size(self):
        rc = replace(RC, risk_pct=1.0)
        r = position_size(10000, 10.0, rc)  # $100 risk, $1000/lot per $10 → 0.10 lot
        assert r["lots"] == pytest.approx(0.10)
        assert r["risk_amount"] <= 100.0 + 1e-9

    def test_position_size_never_inflated(self):
        r = position_size(100, 20.0, replace(RC, risk_pct=0.5))
        assert r["lots"] is None and "minimal lot" in r["note"]

    def _live_inputs(self):
        h4 = _walk(1600, tf=240, drift=0.8, vol=4.0, seed=11, start=datetime(2025, 3, 3))
        now = h4[-1]["timestamp"] + timedelta(hours=4, minutes=5)
        return h4, now

    def test_live_output_contract(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
        h4, now = self._live_inputs()
        if is_market_closed(now):
            pytest.skip("generated series ends in weekend")
        sig = generate(h4, None, now=now)
        for key in ("instrument", "generated_at", "direction", "market_regime", "timeframe_confirmation",
                    "reasons", "reason_codes", "invalidation", "data_status", "spread", "risk_warning",
                    "strategy_version", "config_hash", "signal_score"):
            assert key in sig
        assert sig["direction"] in (BUY, SELL, NO_TRADE)
        line = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
        assert line["config_hash"] == sig["config_hash"]
        v = legacy_view(sig)
        if v["signal_type"] == NO_TRADE:
            assert v["entry"] is None and v["stop_loss"] is None and v["confidence"] == 0.0

    def test_live_blocks_stale_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "a.jsonl"))
        h4, now = self._live_inputs()
        later = now + timedelta(days=3)
        while is_market_closed(later):
            later += timedelta(hours=6)
        sig = generate(h4, None, now=later)
        assert sig["direction"] == NO_TRADE and sig["reason_codes"][0].startswith("DATA_")

    def test_live_blocks_news(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "a.jsonl"))
        h4, now = self._live_inputs()
        if is_market_closed(now):
            pytest.skip("weekend")
        ev = [{"event": "CPI", "currency": "USD", "impact": 3, "event_time": now + timedelta(minutes=10)}]
        sig = generate(h4, None, now=now, events=ev)
        assert sig["direction"] == NO_TRADE and "NEWS_BLACKOUT" in sig["reason_codes"]

    def test_live_missing_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "a.jsonl"))
        h4, now = self._live_inputs()
        if is_market_closed(now):
            pytest.skip("weekend")
        sig = generate(h4[-400:], None, now=now)
        assert sig["direction"] == NO_TRADE and sig["reason_codes"][0].startswith("CONTEXT_")


# ── regression tests for fixed legacy bugs ───────────────────────────────────

def test_gold_ai_engine_can_emit_signal_now():
    """Before the fix RR1 = 1.5·d/(d+0.1·ATR) < 1.5 always → every setup was NO_TRADE."""
    from services.gold_ai_engine import _build_signal
    c = _walk(120, drift=0.5, vol=2.0, seed=5)
    sig = _build_signal("BUY", c, {}, {"order_blocks": []}, 80.0, 1.0, "high", 0,
                        {"confidence": 0}, {}, [], [], {"pattern": "none"}, "H1")
    if sig["status"] == "NO_TRADE":
        assert "RR1" not in (sig["no_trade_reason"] or "")
    else:
        assert sig["rr1"] == pytest.approx(1.5, abs=0.01)


def test_snapshot_has_macd_hist():
    from services.indicator_service import compute_snapshot
    snap = compute_snapshot(_walk(120))
    assert snap["macd_hist"] == pytest.approx(snap["macd"] - snap["macd_signal"], abs=1e-5)


def test_calendar_offset_converted_to_utc():
    from services.calendar_service import _parse_ff_date
    assert _parse_ff_date("2026-05-29T08:30:00-04:00") == datetime(2026, 5, 29, 12, 30)


def test_twelvedata_bad_timestamp_rejected():
    from services.market_service import _parse_td_dt
    assert _parse_td_dt("not-a-date") is None


# ── API: /signals/generate (v2) on a minimal app ─────────────────────────────

def test_generate_endpoint_v2_and_dedup(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base, get_db
    import models  # noqa: F401  (register tables)
    from models.candle import Candle
    import routers.signals as sigmod

    # file-backed DB: the conftest in-memory DB is per-connection, invisible to TestClient's thread
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    h4 = _walk(1600, tf=240, drift=0.8, vol=4.0, seed=11, start=datetime(2025, 3, 3))
    d1 = _walk(400, tf=1440, drift=3.0, vol=15.0, seed=12, start=datetime(2025, 1, 6))
    now = h4[-1]["timestamp"] + timedelta(hours=4, minutes=5)

    s = TestingSessionLocal()
    s.query(Candle).filter(Candle.symbol == "XAUUSD", Candle.timeframe.in_(["240", "1440"])).delete()
    for tf, rows in (("240", h4), ("1440", d1)):
        s.add_all([Candle(symbol="XAUUSD", timeframe=tf, **r) for r in rows])
    s.commit()
    s.close()

    monkeypatch.setattr(sigmod, "fetch_and_store", lambda *a, **k: [])
    monkeypatch.setattr(sigmod, "refresh_calendar", lambda db: None)
    monkeypatch.setattr(sigmod, "alert_signal", lambda sig: 0)

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz) if tz else now
    monkeypatch.setattr(sigmod, "datetime", _FrozenDT)

    app = FastAPI()
    app.include_router(sigmod.router, prefix="/api/v1/signals")

    def override():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        r1 = c.post("/api/v1/signals/generate", json={"symbol": "XAUUSD"})
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["signal_type"] in ("BUY", "SELL", "NO TRADE")
        assert b1["timeframe"] == "240" and "reason_codes" in b1 and "data_status" in b1
        r2 = c.post("/api/v1/signals/generate", json={"symbol": "XAUUSD"}).json()
        assert r2["duplicate"] is True and r2["id"] == b1["id"]
