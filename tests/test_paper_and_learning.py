"""Paper trading, strategy health, registry, learning, execution gate, strategy lab."""
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from paper.broker import Position, process  # noqa: E402
from strategy.backtest import simulate  # noqa: E402
from strategy.config import RiskConfig  # noqa: E402

ZERO = RiskConfig(spread=0.0, slippage=0.0)
T0 = datetime(2026, 3, 3, 8, 0)  # Tuesday


def _pos(**kw):
    base = dict(direction="BUY", status="PENDING", signal_time=T0, expires_at=T0 + timedelta(hours=8),
                entry_ref=100.0, zone_low=97.0, zone_high=101.0, stop_loss=90.0, take_profit=125.0,
                risk_per_oz=10.0, lots=0.1)
    base.update(kw)
    return Position(**base)


def _bars(rows, start=T0, minutes=5):
    return [{"timestamp": start + timedelta(minutes=minutes * k), "open": o, "high": h, "low": l, "close": c}
            for k, (o, h, l, c) in enumerate(rows)]


H8 = timedelta(hours=192)


class TestPaperBroker:
    def test_fill_then_tp(self):
        p = process(_pos(), _bars([(100, 101, 99, 100), (100, 126, 99, 120)]), ZERO, 5, H8)
        assert p.status == "CLOSED" and p.exit_reason == "TP" and p.r_multiple == pytest.approx(2.5)
        assert p.pnl_usd == pytest.approx(25 * 100 * 0.1)

    def test_zone_missed_and_beyond_levels(self):
        assert process(_pos(), _bars([(105, 106, 104, 105)]), ZERO, 5, H8).exit_reason == "ENTRY_ZONE_MISSED"
        p = process(_pos(zone_low=80, zone_high=130), _bars([(89, 90, 88, 89)]), ZERO, 5, H8)
        assert p.exit_reason == "OPENED_BEYOND_LEVELS"

    def test_expired(self):
        p = process(_pos(), _bars([(100, 101, 99, 100)], start=T0 + timedelta(hours=9)), ZERO, 5, H8)
        assert p.status == "CANCELLED" and p.exit_reason == "EXPIRED"

    def test_sl_first_and_costs(self):
        rc = RiskConfig(spread=0.4, slippage=0.1)
        p = process(_pos(), _bars([(100, 130, 85, 100)]), rc, 5, H8)
        assert p.exit_reason == "SL_AMBIGUOUS"
        # fill 100.3, exit 90-0.1 → -10.4/10
        assert p.r_multiple == pytest.approx(-1.04)

    def test_time_exit_counts_trading_minutes(self):
        p = process(_pos(), _bars([(100, 101, 99, 100)] * 4), ZERO, 5, timedelta(minutes=15))
        assert p.exit_reason == "TIME" and p.open_minutes == 15

    def test_incremental_ticks_and_gap_flag(self):
        p = _pos()
        p = process(p, _bars([(100, 101, 99, 100)]), ZERO, 5, H8)
        assert p.status == "OPEN"
        p = process(p, _bars([(100, 101, 99, 100)]), ZERO, 5, H8)  # same bar again → ignored
        assert p.bars_processed == 1
        later = _bars([(100, 101, 99, 100)], start=T0 + timedelta(hours=3))
        p = process(p, later, ZERO, 5, H8)
        assert p.data_gap is True and p.status == "OPEN"

    def test_parity_with_backtester(self):
        """Same bars, same single signal → same exit and R in paper and backtest."""
        rows = [(100, 101, 99, 100), (100, 104, 98, 103), (103, 106, 100, 105), (105, 127, 104, 126)]
        p = process(_pos(signal_time=T0, expires_at=T0 + timedelta(hours=8)), _bars(rows, start=T0), RiskConfig(), 5, H8)
        df = pd.DataFrame(_bars([(100, 100, 100, 100)] + rows, start=T0 - timedelta(minutes=5)))
        sent = {"x": False}

        def decide(i):
            if i == 0 and not sent["x"]:
                sent["x"] = True
                return {"action": "BUY", "entry": 100.0, "stop_loss": 90.0, "take_profit": 125.0,
                        "entry_zone": {"low": 97.0, "high": 101.0}}
            return None
        t = simulate(df, decide, RiskConfig(), 48)["trades"][0]
        assert (p.exit_reason, p.r_multiple) == (t.exit_reason, pytest.approx(t.r, abs=1e-6))


# ── service on SQLite ────────────────────────────────────────────────────────

@pytest.fixture()
def paper_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    import models  # noqa: F401
    monkeypatch.setenv("STRATEGY_REGISTRY_DIR", str(tmp_path / "reg"))
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    eng = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _signal(bar_close="2026-03-03T08:00:00", action="BUY"):
    return {"instrument": "XAUUSD", "primary_tf": 240, "config_hash": "abc", "strategy_version": "v2.0.0",
            "strategy_health": {"risk_multiplier": 1.0}, "id": 1,
            "decision": {"action": action, "bar_close": bar_close, "expires_at": "2026-03-03T16:00:00",
                         "entry": 4000.0, "entry_zone": {"low": 3994.0, "high": 4002.0},
                         "stop_loss": 3980.0, "take_profit": 4050.0, "risk": 20.0, "cost": 0.5,
                         "regime": "TREND_UP", "reasons": ["r"], "signal_score": 70, "score_components": {}}}


class TestPaperService:
    def test_submit_idempotent_and_limits(self, paper_db):
        from paper import service
        r1 = service.submit_signal(paper_db, _signal(), now=T0)
        assert r1["status"] == "pending" and r1["lots"] == pytest.approx(0.02)  # 0.5% of 10k / (20.25*100)
        assert service.submit_signal(paper_db, _signal(), now=T0)["status"] in ("duplicate", "rejected")
        r3 = service.submit_signal(paper_db, _signal(bar_close="2026-03-03T12:00:00"), now=T0)
        assert r3["status"] == "rejected" and r3["reason"].startswith("MAX_OPEN_POSITIONS")

    def test_tick_closes_and_updates_balance(self, paper_db):
        from models.candle import Candle
        from paper import service
        service.submit_signal(paper_db, _signal(), now=T0)
        bars = _bars([(4000, 4001, 3999, 4000), (4000, 4060, 3999, 4055)])
        paper_db.add_all([Candle(symbol="XAUUSD", timeframe="5", volume=0, **b) for b in bars])
        paper_db.commit()
        r = service.tick(paper_db, now=T0 + timedelta(minutes=30), fetch=False)
        assert r["trades"][0]["status"] == "CLOSED" and r["trades"][0]["exit_reason"] == "TP"
        st = service.stats(paper_db)
        assert st["trades"] == 1 and st["account"]["balance"] > st["account"]["start_balance"]
        assert st["account"]["mode"] == "paper"

    def test_disabled(self, paper_db, monkeypatch):
        from paper import service
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        assert service.submit_signal(paper_db, _signal())["status"] == "disabled"


# ── health ───────────────────────────────────────────────────────────────────

class TestHealth:
    REF = {"expectancy_r": 0.5, "std_r": 1.7, "max_drawdown_r": 6.0, "max_consecutive_losses": 6}

    def test_statuses(self):
        from strategy.health import evaluate
        assert evaluate([1.0, -1.0], self.REF).status == "INSUFFICIENT_DATA"
        assert evaluate([2.5, -1, -1, 2.5] * 6, self.REF).status == "OK"
        assert evaluate([1.0] * 5 + [-1.0] * 12, self.REF).status == "SUSPENDED"
        degraded = evaluate([-1.0, -1.0, 1.0] * 8, self.REF)
        assert degraded.status in ("DEGRADED", "SUSPENDED")
        if degraded.status == "DEGRADED":
            assert degraded.risk_multiplier == 0.5

    def test_suspended_blocks_live_signal(self, tmp_path, monkeypatch):
        from strategy.live import generate
        monkeypatch.setenv("SIGNAL_AUDIT_LOG", str(tmp_path / "a.jsonl"))
        sig = generate([], None, health={"status": "SUSPENDED", "reasons": ["x"]})
        assert sig["direction"] == "NO TRADE" and sig["reason_codes"] == ["STRATEGY_SUSPENDED"]


# ── registry ─────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_seed_compare_promote_rollback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_REGISTRY_DIR", str(tmp_path))
        from strategy import registry
        from strategy.config import StrategyConfig
        champ = registry.seed_baseline()
        assert registry.champion()["id"] == champ["id"]
        assert registry.active_config().version_hash() == StrategyConfig().version_hash()

        weak = registry.register("weak", {"target_rr": 3.0},
                                 {"test": {"trades": 10, "expectancy_r_ci95": [-0.5, 0.4]}, "walk_forward": {}},
                                 {}, {"fingerprint": "td_4h_2026-10-22"})
        v = registry.compare(weak["id"])
        assert v["eligible"] is False and len(v["reasons"]) >= 3
        with pytest.raises(PermissionError):
            registry.promote(weak["id"], approved_by="tester")
        with pytest.raises(ValueError):
            registry.promote(weak["id"], approved_by="")

        strong = registry.register("strong", {"target_rr": 2.0},
                                   {"test": {"trades": 80, "expectancy_r_ci95": [0.1, 0.6], "max_drawdown_r": 5},
                                    "walk_forward": {"pooled_oos_trades": 150, "pooled_oos_expectancy_r": 0.35}},
                                   {"expectancy_r": 0.35}, {"fingerprint": "td_4h_2026-10-22"})
        assert registry.compare(strong["id"])["eligible"] is True
        registry.promote(strong["id"], approved_by="tester")
        assert registry.active_config().target_rr == 2.0
        assert registry.get(champ["id"])["status"] == "retired"
        registry.rollback("tester")
        assert registry.champion()["id"] == champ["id"]
        assert registry.active_config().target_rr == 2.5

    def test_unknown_params_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_REGISTRY_DIR", str(tmp_path))
        from strategy import registry
        with pytest.raises(ValueError):
            registry.register("bad", {"no_such_param": 1}, {}, {}, {})


# ── learning ─────────────────────────────────────────────────────────────────

def test_learning_requires_evidence():
    from strategy.learning import analyse
    assert analyse([])["trades"] == 0
    few = analyse([{"r": 1.0, "mfe_r": 1.2, "mae_r": 0.1, "regime": "TREND_UP", "direction": "BUY",
                    "session": "asia", "exit_reason": "TP"}] * 5)
    assert few["ready_for_learning"] is False and few["groups"]["direction"]["BUY"]["status"] == "insufficient"
    many = [{"r": -1.0, "mfe_r": 1.3, "mae_r": 1.0, "regime": "TREND_UP", "direction": "SELL",
             "session": "asia", "exit_reason": "SL"}] * 30
    out = analyse(many)
    assert any("breakeven" in h["hypothesis"] for h in out["hypotheses"])
    assert any("SELL" in h["finding"] for h in out["hypotheses"])


# ── execution gate ───────────────────────────────────────────────────────────

class TestExecutionGate:
    def test_live_always_blocked(self, monkeypatch):
        from execution import gate
        monkeypatch.setenv("TRADING_MODE", "live")
        assert gate.current_mode() == gate.SIGNAL_ONLY  # unimplemented mode never escalates
        great = {"trades": 500, "days": 400, "expectancy_r_ci95": [0.2, 0.6]}
        r = gate.readiness(great, {"status": "OK"})
        assert r["live_allowed"] is False
        assert {c["check"] for c in r["checks"] if not c["passed"]} >= {"broker_adapter_implemented", "explicit_consent"}
        with pytest.raises(gate.LiveTradingBlocked):
            gate.assert_live_allowed(great, {"status": "OK"})

    def test_paper_mode(self, monkeypatch):
        from execution import gate
        monkeypatch.setenv("TRADING_MODE", "paper")
        assert gate.current_mode() == gate.PAPER


def test_no_order_execution_code_in_backend():
    """Guard: nothing in backend/ may call a broker order API."""
    import re
    root = os.path.join(os.path.dirname(__file__), "..", "backend")
    pat = re.compile(r"order_send|OrderSend|place_order\(|mt5\.order|TRADE_ACTION_DEAL")
    hits = []
    for d, _, files in os.walk(root):
        for f in files:
            if f.endswith(".py") and f != "gate.py":
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    if pat.search(fh.read()):
                        hits.append(f)
    assert hits == []


# ── lab ──────────────────────────────────────────────────────────────────────

def test_lab_families_produce_valid_levels():
    from test_strategy_v2 import _walk
    from strategy.engine import attach_context, prepare_context, prepare_primary
    from strategy.lab import FAMILIES, default_cfg, make_decider
    cfg = default_cfg(240, 1440)
    h4 = pd.DataFrame(_walk(1500, tf=240, drift=0.5, vol=6, seed=21, start=datetime(2025, 1, 6)))
    d1 = pd.DataFrame(_walk(400, tf=1440, drift=2, vol=15, seed=22, start=datetime(2024, 1, 1)))
    p = attach_context(prepare_primary(h4, cfg), prepare_context(d1, cfg))
    rc = RiskConfig()
    for fam in FAMILIES:
        dec = make_decider(fam, p, cfg, rc)
        for i in range(300, len(p) - 1):
            d = dec(i)
            if d and d.get("action") in ("BUY", "SELL"):
                s = 1 if d["action"] == "BUY" else -1
                assert s * (d["entry"] - d["stop_loss"]) > 0 and s * (d["take_profit"] - d["entry"]) > 0, fam


def test_paper_and_readiness_endpoints(paper_db, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base, get_db
    import routers.paper as rp
    eng = create_engine(f"sqlite:///{tmp_path / 'api2.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    app = FastAPI()
    app.include_router(rp.router, prefix="/api/v1")

    def ov():
        db = S()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = ov
    with TestClient(app) as c:
        st = c.get("/api/v1/paper/stats").json()
        assert st["account"]["mode"] == "paper" and st["trades"] == 0 and "note" in st
        rd = c.get("/api/v1/execution/readiness").json()
        assert rd["live_allowed"] is False and rd["mode"] in ("signal_only", "paper")
        assert c.get("/api/v1/paper/analysis").json()["trades"] == 0
        assert c.get("/api/v1/strategy/registry").status_code == 200
