"""
ML predictor — loads trained model ensemble and generates probability predictions.
Falls back gracefully when models are not available.
"""
from __future__ import annotations

import glob
import logging
import os
import pickle
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)
MODEL_DIR = os.environ.get("ML_MODEL_DIR", "models")


class MLPredictor:
    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}
        self._feature_names: Optional[List[str]] = None

    def load_latest(self, model_name: str = "ensemble") -> bool:
        """Load the most recently trained models from disk."""
        self._models.clear()
        for model_type in ["xgboost", "lightgbm", "catboost"]:
            pattern = os.path.join(MODEL_DIR, f"{model_name}_{model_type}_*.pkl")
            files = sorted(glob.glob(pattern))
            if not files:
                continue
            latest = files[-1]
            try:
                with open(latest, "rb") as f:
                    data = pickle.load(f)
                self._models[model_type] = data["model"]
                self._feature_names = data.get("feature_names")
                log.info("Loaded %s from %s", model_type, latest)
            except Exception:
                log.exception("Failed to load model from %s", latest)
        return len(self._models) > 0

    def predict(
        self,
        features: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Predict from a feature dict.
        Returns: {"buy_pct": float, "sell_pct": float, "neutral_pct": float,
                  "direction": str, "score": float, "models_used": int}
        """
        if not self._models:
            self.load_latest()

        if not self._models:
            return {
                "buy_pct": 33.3,
                "sell_pct": 33.3,
                "neutral_pct": 33.3,
                "direction": "neutral",
                "score": 50.0,
                "models_used": 0,
                "note": "No trained models available",
            }

        feature_names = self._feature_names or sorted(features.keys())
        x = [[features.get(f, 0.0) for f in feature_names]]

        buy_votes = 0
        sell_votes = 0
        neutral_votes = 0

        for model_type, model in self._models.items():
            try:
                proba = model.predict_proba(x)[0]
                # Label mapping: 0=SELL, 1=BUY, 2=NEUTRAL
                if len(proba) == 3:
                    sell_votes += proba[0]
                    buy_votes += proba[1]
                    neutral_votes += proba[2]
                elif len(proba) == 2:
                    sell_votes += proba[0]
                    buy_votes += proba[1]
            except Exception:
                log.exception("Prediction failed for %s", model_type)

        n = len(self._models)
        buy_pct = buy_votes / n * 100
        sell_pct = sell_votes / n * 100
        neutral_pct = neutral_votes / n * 100 if neutral_votes > 0 else max(0, 100 - buy_pct - sell_pct)

        # Score: >50 bullish, <50 bearish
        score = 50 + (buy_pct - sell_pct) / 2

        if buy_pct > sell_pct and buy_pct > 45:
            direction = "bullish"
        elif sell_pct > buy_pct and sell_pct > 45:
            direction = "bearish"
        else:
            direction = "neutral"

        return {
            "buy_pct": round(buy_pct, 1),
            "sell_pct": round(sell_pct, 1),
            "neutral_pct": round(neutral_pct, 1),
            "direction": direction,
            "score": round(score, 1),
            "models_used": n,
        }


ml_predictor = MLPredictor()
