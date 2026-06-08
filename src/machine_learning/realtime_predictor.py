"""
RealtimePredictor — Har yangi candle kelganda prediction qilib DB ga saqlaydi
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RealtimePredictor:

    def on_new_candle(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if len(candles) < 30:
            return None

        prediction = self._predict_and_save(db_session, symbol, timeframe, candles)

        if prediction is not None:
            try:
                from src.machine_learning.outcome_checker import outcome_checker
                outcome_checker.check_pending(
                    db_session=db_session,
                    symbol=symbol,
                    timeframe=timeframe,
                    current_candle=candles[-1],
                    recent_candles=candles,
                )
            except Exception:
                log.exception("OutcomeChecker xatosi [%s %s]", symbol, timeframe)

        return prediction

    def _predict_and_save(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        try:
            from src.machine_learning.features import feature_engineer
            from src.machine_learning.predictor import ml_predictor
        except ImportError as e:
            log.error("Import xatosi: %s", e)
            return None

        features = feature_engineer.build_features(candles)
        if not features:
            return None

        result = ml_predictor.predict(features)
        if not result.get("model_available", False):
            self._publish_to_redis(symbol, timeframe, result, candles[-1])
            return result

        self._save_prediction(
            db_session=db_session,
            symbol=symbol,
            timeframe=timeframe,
            result=result,
            features=features,
            candle=candles[-1],
        )
        self._publish_to_redis(symbol, timeframe, result, candles[-1])
        return result

    def _save_prediction(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        result: Dict[str, Any],
        features: Dict[str, float],
        candle: Dict[str, Any],
    ) -> None:
        try:
            from src.machine_learning.feedback_models import PredictionLog
        except ImportError:
            log.warning("PredictionLog modeli topilmadi — alembic migration kerak")
            return

        candle_time = candle.get("timestamp")
        if isinstance(candle_time, str):
            candle_time = datetime.fromisoformat(candle_time)
        if candle_time is None:
            candle_time = _utcnow()

        current_price = float(candle.get("close", 0))
        if current_price <= 0:
            return

        try:
            tf_int = int(timeframe)
        except ValueError:
            tf_int = 60
        look_ahead = 12 if tf_int >= 60 else max(3, 720 // tf_int)

        log_entry = PredictionLog(
            symbol=symbol,
            timeframe=timeframe,
            predicted_at=_utcnow(),
            candle_time=candle_time,
            current_price=current_price,
            predicted_dir=result.get("direction", "neutral"),
            buy_pct=result.get("buy_pct"),
            sell_pct=result.get("sell_pct"),
            neutral_pct=result.get("neutral_pct"),
            confidence=result.get("score"),
            look_ahead=look_ahead,
            features_json=json.dumps(
                {k: round(v, 6) for k, v in list(features.items())[:50]}
            ),
            outcome_checked=False,
        )
        try:
            db_session.add(log_entry)
            db_session.commit()
        except Exception:
            db_session.rollback()
            log.exception("PredictionLog yozishda xato")

    def _publish_to_redis(
        self,
        symbol: str,
        timeframe: str,
        result: Dict[str, Any],
        candle: Dict[str, Any],
    ) -> None:
        try:
            from src.storage.redis_store import publish
            publish(
                f"indicator-updates:{symbol}",
                {
                    "type": "ml_prediction",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": result.get("direction"),
                    "buy_pct": result.get("buy_pct"),
                    "sell_pct": result.get("sell_pct"),
                    "score": result.get("score"),
                    "models_used": result.get("models_used", 0),
                    "model_available": result.get("model_available", False),
                    "timestamp": _utcnow().isoformat(),
                },
            )
        except Exception:
            log.debug("Redis publish xatosi", exc_info=True)


realtime_predictor = RealtimePredictor()
