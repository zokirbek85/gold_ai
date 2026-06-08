"""
OutcomeChecker — Predictionlar natijasini tekshiruvchi
======================================================
Har yangi candle kelganda:
1. Tekshirilmagan prediction_log yozuvlarini topadi
2. look_ahead bar o'tgan bo'lsa natijani hisoblaydi
3. prediction_result jadvaliga yozadi
4. Xato bo'lsa error_pattern jadvalini yangilaydi
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _market_session(dt: datetime) -> str:
    h = dt.hour
    if 7 <= h < 16:
        return "london"
    elif 13 <= h < 22:
        return "newyork"
    return "asian"


def _price_direction(change_pct: float, threshold: float = 0.3) -> str:
    if change_pct > threshold:
        return "bullish"
    elif change_pct < -threshold:
        return "bearish"
    return "neutral"


class OutcomeChecker:

    def check_pending(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        current_candle: Dict[str, Any],
        recent_candles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            from src.machine_learning.feedback_models import (
                PredictionLog, PredictionResult, ErrorPattern
            )
        except ImportError:
            log.warning("feedback_models import qilinmadi — alembic migrate qilindimi?")
            return {"checked": 0, "correct": 0, "wrong": 0, "accuracy": 0.0}

        pending = (
            db_session.query(PredictionLog)
            .filter(
                PredictionLog.symbol == symbol,
                PredictionLog.timeframe == timeframe,
                PredictionLog.outcome_checked == False,  # noqa: E712
            )
            .all()
        )

        if not pending:
            return {"checked": 0, "correct": 0, "wrong": 0, "accuracy": 0.0}

        current_time = current_candle.get("timestamp")
        if isinstance(current_time, str):
            current_time = datetime.fromisoformat(current_time)
        current_price = float(current_candle["close"])

        try:
            from src.indicators.calculator import calculator as ind_calc
            indicators = ind_calc.compute_all(recent_candles) if len(recent_candles) >= 20 else {}
        except Exception:
            indicators = {}

        checked = correct = wrong = 0

        for pred in pending:
            pred_time = pred.candle_time
            if pred_time.tzinfo is not None:
                pred_time = pred_time.replace(tzinfo=None)

            try:
                tf_minutes = int(timeframe)
            except ValueError:
                tf_minutes = 60

            delta_minutes = (current_time - pred_time).total_seconds() / 60
            if delta_minutes < pred.look_ahead * tf_minutes:
                continue

            entry_price = pred.current_price
            change_pct = (current_price - entry_price) / entry_price * 100
            actual_dir = _price_direction(change_pct)

            was_correct = (
                pred.predicted_dir == actual_dir
                or (pred.predicted_dir == "neutral" and abs(change_pct) <= 0.3)
            )

            result_row = PredictionResult(
                prediction_id=pred.id,
                symbol=symbol,
                timeframe=timeframe,
                predicted_at=pred.predicted_at,
                resolved_at=_utcnow(),
                predicted_dir=pred.predicted_dir,
                actual_dir=actual_dir,
                entry_price=entry_price,
                exit_price=current_price,
                price_change_pct=round(change_pct, 4),
                was_correct=was_correct,
                market_volatility=indicators.get("ATR_14"),
                trend_strength=indicators.get("ADX"),
                rsi_at_signal=indicators.get("RSI_14"),
                session=_market_session(pred.predicted_at),
            )
            db_session.add(result_row)
            pred.outcome_checked = True

            if not was_correct:
                self._update_error_pattern(
                    db_session=db_session,
                    ErrorPattern=ErrorPattern,
                    symbol=symbol,
                    timeframe=timeframe,
                    predicted_dir=pred.predicted_dir,
                    actual_dir=actual_dir,
                    indicators=indicators,
                    session=_market_session(pred.predicted_at),
                )
                wrong += 1
            else:
                correct += 1

            checked += 1

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            log.exception("OutcomeChecker commit xatosi")
            return {"checked": 0, "correct": 0, "wrong": 0, "accuracy": 0.0}

        accuracy = correct / checked if checked > 0 else 0.0
        log.info(
            "OutcomeChecker [%s %s]: %d tekshirildi, %d to'g'ri, %d xato (%.1f%%)",
            symbol, timeframe, checked, correct, wrong, accuracy * 100,
        )
        return {"checked": checked, "correct": correct, "wrong": wrong,
                "accuracy": round(accuracy, 4)}

    def _update_error_pattern(
        self,
        db_session: Any,
        ErrorPattern: Any,
        symbol: str,
        timeframe: str,
        predicted_dir: str,
        actual_dir: str,
        indicators: Dict[str, Any],
        session: str,
    ) -> None:
        rsi = indicators.get("RSI_14", 50.0)
        adx = indicators.get("ADX", 20.0)
        atr = indicators.get("ATR_14", 0)
        atr_pct = float(atr) * 0.0001 if atr else 0.0

        if rsi > 70 and predicted_dir == "bullish":
            pattern_type = "overbought_buy_fail"
        elif rsi < 30 and predicted_dir == "bearish":
            pattern_type = "oversold_sell_fail"
        elif adx < 20 and predicted_dir != "neutral":
            pattern_type = "weak_trend_signal_fail"
        elif adx > 40 and predicted_dir != actual_dir:
            pattern_type = "strong_trend_counter_fail"
        elif session == "asian" and predicted_dir != "neutral":
            pattern_type = "asian_session_directional_fail"
        else:
            pattern_type = f"general_{predicted_dir}_fail"

        existing = (
            db_session.query(ErrorPattern)
            .filter(
                ErrorPattern.symbol == symbol,
                ErrorPattern.timeframe == timeframe,
                ErrorPattern.pattern_type == pattern_type,
            )
            .first()
        )

        if existing:
            existing.occurrence_count += 1
            n = existing.occurrence_count
            existing.error_rate = min(1.0, existing.error_rate + (1.0 - existing.error_rate) / n)
            existing.weight_penalty = min(0.5, existing.weight_penalty + 0.02)
        else:
            desc = (
                f"RSI={rsi:.0f}, ADX={adx:.0f}, session={session}: "
                f"{predicted_dir} predicted lekin {actual_dir} bo'ldi"
            )
            pattern = ErrorPattern(
                symbol=symbol,
                timeframe=timeframe,
                pattern_type=pattern_type,
                rsi_range_low=round(rsi - 5, 1),
                rsi_range_high=round(rsi + 5, 1),
                adx_range_low=round(adx - 5, 1),
                adx_range_high=round(adx + 5, 1),
                volatility_low=max(0.0, round(atr_pct - 0.001, 4)),
                volatility_high=round(atr_pct + 0.001, 4),
                session=session,
                was_predicted=predicted_dir,
                correct_was=actual_dir,
                occurrence_count=1,
                error_rate=1.0,
                weight_penalty=0.1,
                description=desc,
            )
            db_session.add(pattern)

    def get_recent_accuracy(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        last_n: int = 100,
    ) -> Dict[str, Any]:
        try:
            from src.machine_learning.feedback_models import PredictionResult
        except ImportError:
            return {"accuracy": None, "count": 0, "message": "Jadvallar topilmadi"}

        rows = (
            db_session.query(PredictionResult)
            .filter(
                PredictionResult.symbol == symbol,
                PredictionResult.timeframe == timeframe,
            )
            .order_by(PredictionResult.resolved_at.desc())
            .limit(last_n)
            .all()
        )

        if not rows:
            return {"accuracy": None, "count": 0, "message": "Hali natijalar yo'q"}

        correct = sum(1 for r in rows if r.was_correct)
        total = len(rows)
        by_session: Dict[str, Dict[str, int]] = {}
        for r in rows:
            s = r.session or "unknown"
            if s not in by_session:
                by_session[s] = {"correct": 0, "total": 0}
            by_session[s]["total"] += 1
            if r.was_correct:
                by_session[s]["correct"] += 1

        session_accuracy = {
            s: round(v["correct"] / v["total"], 4)
            for s, v in by_session.items()
        }
        return {
            "accuracy": round(correct / total, 4),
            "correct": correct,
            "wrong": total - correct,
            "count": total,
            "session_accuracy": session_accuracy,
        }

    def get_error_patterns_summary(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        min_occurrences: int = 3,
    ) -> List[Dict[str, Any]]:
        try:
            from src.machine_learning.feedback_models import ErrorPattern
        except ImportError:
            return []

        patterns = (
            db_session.query(ErrorPattern)
            .filter(
                ErrorPattern.symbol == symbol,
                ErrorPattern.timeframe == timeframe,
                ErrorPattern.occurrence_count >= min_occurrences,
            )
            .order_by(ErrorPattern.error_rate.desc())
            .limit(20)
            .all()
        )
        return [
            {
                "pattern_type": p.pattern_type,
                "description": p.description,
                "occurrences": p.occurrence_count,
                "error_rate": p.error_rate,
                "weight_penalty": p.weight_penalty,
                "session": p.session,
                "detected_at": p.detected_at.isoformat() if p.detected_at else None,
            }
            for p in patterns
        ]


outcome_checker = OutcomeChecker()
