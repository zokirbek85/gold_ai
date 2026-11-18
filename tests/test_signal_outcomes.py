"""Signal outcome tracking, performance stats and the legacy quality gate."""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.candle import Candle  # noqa: E402
from models.signal import Signal  # noqa: E402
from services import signal_outcomes as so  # noqa: E402

T0 = datetime(2026, 3, 3, 8, 0)  # Tuesday
NOW = T0 + timedelta(days=2)


def _bars(db, symbol, rows, tf="5", start=T0, minutes=5):
    for k, (o, h, l, c) in enumerate(rows):
        db.add(Candle(symbol=symbol, timeframe=tf, timestamp=start + timedelta(minutes=minutes * k),
                      open=o, high=h, low=l, close=c, volume=0.0))
    db.commit()


def _flat(n, px=4000.0):
    return [(px, px + 0.5, px - 0.5, px)] * n


def _sig(db, symbol, side="BUY", entry=4000.0, sl=3990.0, tp=4025.0, tf="60", tp1=4010.0,
         created=T0, conf=55.0):
    s = Signal(symbol=symbol, timeframe=tf, signal_type=side, entry=entry, stop_loss=sl, take_profit=tp,
               tp1=tp1, confidence=conf, created_at=created)
    db.add(s)
    db.commit()
    return s


def _resolve(db):
    return so.resolve_pending(db, now=NOW, fetch=False)


class TestResolve:
    def test_buy_fills_then_hits_tp(self, db):
        _bars(db, "T1", _flat(2) + [(4001, 4026, 4000, 4024)] + _flat(5, 4024))
        s = _sig(db, "T1")
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "TP" and s.status == "tp_hit" and s.resolution_tf == "5"
        assert 2.3 < s.outcome_r < 2.5          # 2.5R minus spread/slippage
        assert s.tp1_hit is True and s.mfe_r >= 2.5

    def test_sl_first_when_both_touched_in_one_bar(self, db):
        _bars(db, "T2", _flat(1) + [(4000, 4030, 3985, 4000)] + _flat(3))
        s = _sig(db, "T2")
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "SL_AMBIGUOUS" and s.status == "sl_hit" and s.outcome_r < -1.0

    def test_sell_side(self, db):
        _bars(db, "T3", _flat(1) + [(4000, 4001, 3974, 3976)] + _flat(3, 3976))
        s = _sig(db, "T3", side="SELL", sl=4010.0, tp=3975.0, tp1=3990.0)
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "TP" and s.outcome_r > 2.0

    def test_zone_missed_is_not_filled_and_has_no_r(self, db):
        _bars(db, "T4", _flat(4, 4008))   # opens 0.8R away; zone is ±0.25R
        s = _sig(db, "T4")
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "ENTRY_ZONE_MISSED" and s.status == "not_filled" and s.outcome_r is None

    def test_open_position_waits_for_more_bars(self, db):
        _bars(db, "T5", _flat(6))
        s = _sig(db, "T5", created=NOW - timedelta(hours=1))
        _bars(db, "T5", _flat(6), start=NOW - timedelta(minutes=55))
        _resolve(db)
        db.refresh(s)
        assert s.outcome is None and s.status == "active"

    def test_falls_back_to_h1_when_no_m5(self, db):
        _bars(db, "T6", [(4000, 4002, 3998, 4001), (4001, 4030, 4000, 4028)] + _flat(3, 4028),
              tf="60", minutes=60)
        s = _sig(db, "T6")
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "TP" and s.resolution_tf == "60"

    def test_invalid_levels(self, db):
        s = _sig(db, "T7", sl=4010.0)   # BUY with SL above entry
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "INVALID"

    def test_no_data_after_three_weeks(self, db):
        s = _sig(db, "T8", created=NOW - timedelta(days=30))
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "NO_DATA" and s.outcome_r is None

    def test_paper_linked_signal_copies_paper_result(self, db):
        from models.paper import PaperAccount, PaperTrade
        acc = db.query(PaperAccount).first()
        if acc is None:
            acc = PaperAccount(name="t-outcomes", start_balance=1e4, balance=1e4, peak_balance=1e4)
            db.add(acc)
            db.commit()
        s = _sig(db, "T9", tf="240")
        db.add(PaperTrade(account_id=acc.id, signal_key="T9|x", signal_id=s.id, strategy="trend_pullback",
                          strategy_version="v", config_hash="h", direction="BUY", status="CLOSED",
                          signal_time=T0, expires_at=T0, entry_ref=4000, zone_low=3999, zone_high=4001,
                          stop_loss=3990, take_profit=4025, risk_per_oz=10, lots=0.1, spread=0.3, slippage=0.1, fill_price=4000.2,
                          fill_time=T0, exit_price=3989.9, exit_time=T0 + timedelta(hours=4),
                          exit_reason="SL", r_multiple=-1.03, mfe_r=0.4, mae_r=1.0))
        db.commit()
        _resolve(db)
        db.refresh(s)
        assert s.outcome == "SL" and s.resolution_tf == "paper" and s.outcome_r == pytest.approx(-1.03)

    def test_idempotent(self, db):
        _bars(db, "T10", _flat(1) + [(4001, 4026, 4000, 4024)] + _flat(2, 4024))
        s = _sig(db, "T10")
        _resolve(db)
        db.refresh(s)
        first = (s.outcome, s.outcome_r, s.resolved_at)
        _resolve(db)
        db.refresh(s)
        assert (s.outcome, s.outcome_r, s.resolved_at) == first


class TestSummary:
    def test_summary_numbers(self):
        r = so.summarize([2.0, -1.0, -1.0, 2.0, -1.0])
        assert r["trades"] == 5 and r["win_rate"] == 40.0
        assert r["expectancy_r"] == pytest.approx(0.2) and r["profit_factor"] == pytest.approx(4 / 3, abs=0.01)
        assert r["max_consecutive_losses"] == 2 and r["max_drawdown_r"] == pytest.approx(-2.0)
        assert r["reliable"] is False   # n < 30

    def test_empty(self):
        assert so.summarize([]) == {"trades": 0}

    def test_sessions(self):
        assert so.session_of(3) == "asia" and so.session_of(13) == "london_ny_overlap"
        assert so.session_of(22) == "rollover" and so.session_of(17) == "new_york"

    def test_performance_groups_and_calibration(self, db):
        _bars(db, "P1", _flat(1) + [(4001, 4026, 4000, 4024)] + _flat(2, 4024))
        _sig(db, "P1", conf=85.0)
        _resolve(db)
        out = so.performance(db, symbol="P1")
        assert out["overall"]["trades"] == 1 and "60" in out["by_timeframe"]
        assert out["confidence_calibration"][0]["bucket"] == "80-100"
        assert out["equity_curve"][-1]["cum_r"] > 2 and out["notes"]


class TestQualityGate:
    @staticmethod
    def _gate(**kw):
        from routers.signals import apply_quality_gate
        base = {"signal_type": "BUY", "timeframe": "60", "rr": 2.0, "stop_loss": 1.0, "take_profit": 3.0,
                "tp1": 2.0, "reasoning": "x"}
        base.update(kw)
        return apply_quality_gate(base)

    def test_low_timeframe_blocked(self):
        r = self._gate(timeframe="5")
        assert r["signal_type"] == "NO TRADE" and r["original_signal_type"] == "BUY"
        assert r["stop_loss"] is None and "QUALITY_GATE" in r["reasoning"]

    def test_low_rr_blocked(self):
        assert self._gate(rr=1.2)["signal_type"] == "NO TRADE"

    def test_good_signal_passes(self):
        r = self._gate(timeframe="240", rr=2.5)
        assert r["signal_type"] == "BUY" and r["stop_loss"] == 1.0

    def test_no_trade_untouched(self):
        assert self._gate(signal_type="NO TRADE", timeframe="1")["signal_type"] == "NO TRADE"


def test_event_impact_nearest_bar_without_strftime(db):
    """Regression: SQLite-only strftime('%s') broke on Postgres and poisoned the session."""
    from models.economic_calendar import EconomicEvent
    from services.historical_analysis import event_impact_analysis
    start = datetime(2025, 1, 6)
    for i in range(4):
        et = start + timedelta(days=7 * i, hours=13)
        db.add(EconomicEvent(event=f"CPI test {i}", currency="USD", impact="high", event_time=et))
        _bars(db, "EV", [(4000 + i, 4001 + i, 3999 + i, 4000 + i)] * 32, tf="60",
              start=et - timedelta(hours=6), minutes=60)
    db.commit()
    out = event_impact_analysis(db, "EV", ["CPI test"])
    assert not out.get("insufficient_data")
