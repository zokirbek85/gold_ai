"""
IncrementalTrainer — Xato tahlili bilan boyitilgan incremental retraining
=========================================================================
Trigger shartlari (env bilan konfiguratsiya):
  ML_RETRAIN_MIN_ERRORS=5       — yangi xato soni
  ML_RETRAIN_MIN_CANDLES=50     — yangi candle soni
  ML_RETRAIN_MAX_INTERVAL_H=2   — maksimal kutish soati
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MIN_NEW_ERRORS       = int(os.environ.get("ML_RETRAIN_MIN_ERRORS", "5"))
MIN_NEW_CANDLES      = int(os.environ.get("ML_RETRAIN_MIN_CANDLES", "50"))
MAX_RETRAIN_INTERVAL = timedelta(hours=float(os.environ.get("ML_RETRAIN_MAX_INTERVAL_H", "2")))
MIN_DATASET_SIZE     = int(os.environ.get("ML_RETRAIN_MIN_DATASET", "100"))

_last_retrain: Dict[str, datetime] = {}
_candles_since_retrain: Dict[str, int] = {}
_errors_since_retrain: Dict[str, int] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class IncrementalTrainer:

    def notify_new_candle(self, symbol: str, timeframe: str) -> None:
        key = f"{symbol}:{timeframe}"
        _candles_since_retrain[key] = _candles_since_retrain.get(key, 0) + 1

    def notify_new_error(self, symbol: str, timeframe: str) -> None:
        key = f"{symbol}:{timeframe}"
        _errors_since_retrain[key] = _errors_since_retrain.get(key, 0) + 1

    def maybe_retrain(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
        force: bool = False,
    ) -> Dict[str, Any]:
        key = f"{symbol}:{timeframe}"
        now = _utcnow()
        last = _last_retrain.get(key)
        new_errors = _errors_since_retrain.get(key, 0)
        new_candles = _candles_since_retrain.get(key, 0)

        if not force:
            if last is not None and (now - last) < timedelta(minutes=30):
                return {"retrained": False, "reason": "too_soon", "metrics": {}}

            time_trigger   = last is not None and (now - last) > MAX_RETRAIN_INTERVAL
            error_trigger  = new_errors >= MIN_NEW_ERRORS
            candle_trigger = new_candles >= MIN_NEW_CANDLES

            if not (time_trigger or error_trigger or candle_trigger):
                return {
                    "retrained": False,
                    "reason": "trigger_not_met",
                    "new_errors": new_errors,
                    "new_candles": new_candles,
                    "metrics": {},
                }

        result = self._retrain_with_error_penalties(db_session, symbol, timeframe, candles)

        if result.get("retrained"):
            _last_retrain[key] = now
            _candles_since_retrain[key] = 0
            _errors_since_retrain[key] = 0

        return result

    def _retrain_with_error_penalties(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            from src.machine_learning.features import feature_engineer
            from src.machine_learning.trainer import MLTrainer
            from src.machine_learning.feedback_models import ErrorPattern
        except ImportError as e:
            log.error("Import xatosi: %s", e)
            return {"retrained": False, "reason": str(e), "metrics": {}}

        error_patterns = (
            db_session.query(ErrorPattern)
            .filter(
                ErrorPattern.symbol == symbol,
                ErrorPattern.timeframe == timeframe,
            )
            .all()
        )

        log.info(
            "IncrementalTrainer [%s %s]: %d error pattern topildi",
            symbol, timeframe, len(error_patterns),
        )

        if len(candles) < 200:
            return {
                "retrained": False,
                "reason": "insufficient_candles",
                "candles": len(candles),
                "metrics": {},
            }

        raw_dataset = feature_engineer.build_dataset(candles, look_ahead=12)
        if len(raw_dataset) < MIN_DATASET_SIZE:
            return {
                "retrained": False,
                "reason": "dataset_too_small",
                "dataset_size": len(raw_dataset),
                "metrics": {},
            }

        enriched_dataset = self._apply_error_penalties(raw_dataset, error_patterns)

        trainer = MLTrainer()
        train_result = trainer.train(enriched_dataset, model_name=f"{symbol}_{timeframe}")

        if "error" in train_result:
            return {"retrained": False, "reason": train_result["error"], "metrics": {}}

        self._log_retrain(db_session, symbol, timeframe, train_result, len(error_patterns))

        log.info(
            "IncrementalTrainer [%s %s]: yangilandi! version=%s, samples=%d, penalties=%d",
            symbol, timeframe,
            train_result.get("version"),
            train_result.get("sample_count", 0),
            len(error_patterns),
        )

        return {
            "retrained": True,
            "reason": "ok",
            "metrics": train_result,
            "error_patterns_applied": len(error_patterns),
        }

    def _apply_error_penalties(
        self,
        dataset: List[Dict[str, Any]],
        error_patterns: List[Any],
    ) -> List[Dict[str, Any]]:
        if not error_patterns:
            return [{**s, "weight": 1.0} for s in dataset]

        enriched = []
        for sample in dataset:
            features = sample.get("features", {})
            rsi = features.get("RSI_14", 50.0)
            adx = features.get("ADX", 20.0)
            weight = 1.0

            for ep in error_patterns:
                rsi_match = (
                    ep.rsi_range_low is not None
                    and ep.rsi_range_high is not None
                    and ep.rsi_range_low <= rsi <= ep.rsi_range_high
                )
                adx_match = (
                    ep.adx_range_low is not None
                    and ep.adx_range_high is not None
                    and ep.adx_range_low <= adx <= ep.adx_range_high
                )
                if rsi_match and adx_match:
                    penalty = getattr(ep, "weight_penalty", 0.1)
                    weight = max(0.1, weight - penalty)

            enriched.append({**sample, "weight": round(weight, 4)})

        penalized = sum(1 for s in enriched if s["weight"] < 1.0)
        log.debug("Penalty qo'llandi: %d / %d sample", penalized, len(enriched))
        return enriched

    def _log_retrain(
        self,
        db_session: Any,
        symbol: str,
        timeframe: str,
        train_result: Dict[str, Any],
        pattern_count: int,
    ) -> None:
        try:
            from src.database.models import SystemLog
            entry = SystemLog(
                level="INFO",
                source="IncrementalTrainer",
                message=(
                    f"[{symbol} {timeframe}] Model yangilandi: "
                    f"version={train_result.get('version')}, "
                    f"samples={train_result.get('sample_count', 0)}, "
                    f"error_patterns={pattern_count}, "
                    f"models={train_result.get('trained_models', [])}"
                ),
            )
            db_session.add(entry)
            db_session.commit()
        except Exception:
            log.debug("SystemLog yozishda xato (muhim emas)")


incremental_trainer = IncrementalTrainer()
