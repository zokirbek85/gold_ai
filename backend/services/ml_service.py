"""
Machine Learning service using scikit-learn RandomForestClassifier.
Trains on historical candle data and generates buy/sell/neutral predictions.
"""
from __future__ import annotations

import logging
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from config import settings
from services.indicator_service import build_ml_features
from services import smc_service

log = logging.getLogger(__name__)


def _model_path(symbol: str, timeframe: str) -> str:
    os.makedirs(settings.ML_MODEL_DIR, exist_ok=True)
    return os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")


def _build_dataset(candles: List[Dict[str, Any]]) -> Tuple[List[List[float]], List[int]]:
    """Build feature matrix X and label vector y."""
    X: List[List[float]] = []
    y: List[int] = []
    FEATURE_NAMES = [
        "rsi", "macd", "macd_signal", "macd_hist",
        "ema_20_dist", "ema_50_dist", "ema_200_dist",
        "atr_pct", "bb_position",
        "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
        "volume_ratio", "smc_score",
    ]

    for i in range(50, len(candles) - 5):
        window = candles[:i + 1]
        smc_val = smc_service.score(window[-100:]).get("score", 50)
        feats = build_ml_features(window, smc_score=smc_val)
        if not feats:
            continue

        current_close = float(candles[i]["close"])
        future_close = float(candles[i + 5]["close"])

        if future_close > current_close * 1.001:
            label = 1
        elif future_close < current_close * 0.999:
            label = -1
        else:
            label = 0

        X.append([feats.get(k, 0.0) for k in FEATURE_NAMES])
        y.append(label)

    return X, y


def train(symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Train a RandomForestClassifier and save to disk."""
    if len(candles) < 200:
        return {"status": "error", "message": "Need at least 200 candles", "accuracy": 0.0, "samples": 0}

    training_candles = candles[-1000:]
    X, y = _build_dataset(training_candles)

    if len(X) < 50:
        return {"status": "error", "message": "Not enough samples after feature engineering", "accuracy": 0.0, "samples": len(X)}

    X_arr = np.array(X)
    y_arr = np.array(y)

    X_train, X_test, y_train, y_test = train_test_split(X_arr, y_arr, test_size=0.2, shuffle=False)

    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    acc = float(accuracy_score(y_test, preds))

    path = _model_path(symbol, timeframe)
    with open(path, "wb") as f:
        pickle.dump({"model": model, "accuracy": acc, "trained_at": datetime.utcnow().isoformat()}, f)

    log.info("Trained model for %s %s: acc=%.3f samples=%d", symbol, timeframe, acc, len(X))
    return {
        "status": "ok",
        "version": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "accuracy": round(acc, 4),
        "samples": len(X),
        "sample_count": len(X),
        "trained_models": ["RandomForestClassifier"],
        "metrics": {
            "RandomForestClassifier": {
                "accuracy": round(acc, 4),
                "samples": len(X),
            }
        },
        "message": f"Model trained successfully with {len(X)} samples, accuracy={acc:.3f}",
    }


def predict(symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Load model and generate a prediction."""
    path = _model_path(symbol, timeframe)
    model_data: Optional[Dict] = None

    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                model_data = pickle.load(f)
        except Exception:
            log.exception("Failed to load model from %s", path)

    smc_val = smc_service.score(candles[-100:]).get("score", 50) if len(candles) >= 100 else 50.0
    features = build_ml_features(candles, smc_score=smc_val)

    if not model_data:
        return {
            "status": "error",
            "message": "No trained ML model found for this symbol/timeframe. Train with real historical data first.",
        }

    if not features:
        return {
            "status": "error",
            "message": "Not enough indicator features for ML prediction. Try a longer range.",
        }

    FEATURE_NAMES = [
        "rsi", "macd", "macd_signal", "macd_hist",
        "ema_20_dist", "ema_50_dist", "ema_200_dist",
        "atr_pct", "bb_position",
        "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
        "volume_ratio", "smc_score",
    ]

    x = np.array([[features.get(k, 0.0) for k in FEATURE_NAMES]])
    model = model_data["model"]
    pred = int(model.predict(x)[0])
    proba = model.predict_proba(x)[0]
    class_pct = {int(cls): round(float(p) * 100, 1) for cls, p in zip(model.classes_, proba)}
    buy_pct = class_pct.get(1, 0.0)
    sell_pct = class_pct.get(-1, 0.0)
    neutral_pct = class_pct.get(0, 0.0)
    confidence = round(max(buy_pct, sell_pct, neutral_pct), 1)
    score = round(buy_pct + neutral_pct * 0.5, 1)

    direction_map = {1: "bullish", -1: "bearish", 0: "neutral"}
    return {
        "status": "ok",
        "direction": direction_map.get(pred, "neutral"),
        "score": score,
        "buy_pct": buy_pct,
        "sell_pct": sell_pct,
        "neutral_pct": neutral_pct,
        "confidence": confidence,
        "features": {k: round(v, 4) for k, v in features.items()},
        "model_accuracy": round(model_data.get("accuracy", 0.0), 4),
        "models_used": 1,
    }
