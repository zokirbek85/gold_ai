"""
Unified ML ensemble: RandomForest (baseline) + XGBoost + LightGBM + CatBoost.

- Trains all available estimators on the same dataset.
- Prediction = weighted soft-voting (accuracy-weighted probabilities).
- Walk-forward validation for unbiased accuracy estimates.
- Serialises each model independently to ML_MODEL_DIR.
- Falls back gracefully if any optional library is missing.
"""
from __future__ import annotations

import logging
import os
import pickle
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from core.constants import ML_FEATURE_NAMES
from config import settings

log = logging.getLogger(__name__)


# ── Walk-forward validation ───────────────────────────────────────────────────

def walk_forward_accuracy(
    model,
    X: List[List[float]],
    y: List[int],
    n_splits: int = 5,
) -> float:
    """
    Time-series walk-forward cross-validation.
    Each fold: train on past, test on immediate future slice.
    Returns mean accuracy across all test folds.
    """
    n = len(X)
    fold_size = n // (n_splits + 1)
    if fold_size < 10:
        return 0.0

    scores: List[float] = []
    for i in range(1, n_splits + 1):
        train_end = i * fold_size
        test_end  = train_end + fold_size
        if test_end > n:
            break
        X_tr, y_tr = X[:train_end], y[:train_end]
        X_te, y_te = X[train_end:test_end], y[train_end:test_end]
        try:
            clone_model = _clone_model(model)
            clone_model.fit(np.array(X_tr), np.array(y_tr))
            preds = clone_model.predict(np.array(X_te))
            scores.append(float(accuracy_score(y_te, preds)))
        except Exception as exc:
            log.debug("Walk-forward fold %d failed: %s", i, exc)

    return round(float(np.mean(scores)) if scores else 0.0, 4)


def _clone_model(model) -> Any:
    """Create an unfitted copy of a sklearn-compatible model."""
    from sklearn.base import clone
    return clone(model)


# ── Single-model training ─────────────────────────────────────────────────────

def _train_single(
    model_type: str,
    X: List[List[float]],
    y: List[int],
) -> Tuple[Optional[Any], float]:
    """
    Train one estimator. Returns (model, walk_forward_accuracy).
    Returns (None, 0.0) if the library is not installed.
    """
    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y)

    model = None
    try:
        if model_type == "random_forest":
            model = RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1,
            )
        elif model_type == "xgboost":
            from xgboost import XGBClassifier
            # Map labels: -1→0, 0→1, 1→2 for XGBoost multi-class
            y_arr_xgb = y_arr + 1
            model = XGBClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.05,
                eval_metric="mlogloss", verbosity=0, random_state=42,
            )
            model.fit(X_arr, y_arr_xgb)
            acc = walk_forward_accuracy(model, X, (y_arr + 1).tolist())
            return model, acc
        elif model_type == "lightgbm":
            from lightgbm import LGBMClassifier
            model = LGBMClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.05, verbose=-1, random_state=42,
            )
        elif model_type == "catboost":
            from catboost import CatBoostClassifier
            model = CatBoostClassifier(
                iterations=100, depth=5, learning_rate=0.05, verbose=0, random_seed=42,
            )
        else:
            return None, 0.0
    except ImportError:
        log.debug("%s not installed — skipping", model_type)
        return None, 0.0
    except Exception as exc:
        log.warning("Failed to init %s: %s", model_type, exc)
        return None, 0.0

    if model is None:
        return None, 0.0

    model.fit(X_arr, y_arr)
    acc = walk_forward_accuracy(model, X, y)
    return model, acc


# ── Ensemble trainer ──────────────────────────────────────────────────────────

class EnsembleTrainer:
    MODEL_TYPES = ["random_forest", "xgboost", "lightgbm", "catboost"]

    def train(
        self,
        candles_features: List[Dict[str, Any]],
        symbol: str,
        timeframe: str,
    ) -> Dict[str, Any]:
        """
        Build X/y from pre-computed features, train all available models,
        save to ML_MODEL_DIR, return metrics dict.

        candles_features: list of {"features": {name: float, ...}, "label": int}
        """
        if len(candles_features) < 100:
            return {"status": "error", "message": f"Need ≥100 samples, got {len(candles_features)}"}

        X = [[row["features"].get(k, 0.0) for k in ML_FEATURE_NAMES]
             for row in candles_features]
        y = [int(row["label"]) for row in candles_features]

        os.makedirs(settings.ML_MODEL_DIR, exist_ok=True)
        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        trained: Dict[str, Any] = {}

        for mt in self.MODEL_TYPES:
            model, acc = _train_single(mt, X, y)
            if model is None:
                continue
            path = os.path.join(
                settings.ML_MODEL_DIR,
                f"{symbol.lower()}_{timeframe}_{mt}.pkl",
            )
            with open(path, "wb") as f:
                pickle.dump({
                    "model": model,
                    "model_type": mt,
                    "accuracy": acc,
                    "feature_names": ML_FEATURE_NAMES,
                    "version": version,
                    "trained_at": datetime.now(timezone.utc).isoformat(),
                }, f)
            trained[mt] = {"accuracy": acc, "path": path}
            log.info("Trained %s for %s %s: wf_acc=%.3f", mt, symbol, timeframe, acc)

        # Also write the legacy "flat" RandomForest model path for backward compat
        if "random_forest" in trained:
            legacy_path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
            with open(legacy_path, "wb") as f:
                rf_path = os.path.join(
                    settings.ML_MODEL_DIR,
                    f"{symbol.lower()}_{timeframe}_random_forest.pkl",
                )
                if os.path.exists(rf_path):
                    with open(rf_path, "rb") as src:
                        pickle.dump(pickle.load(src), f)

        return {
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "version": version,
            "trained_models": list(trained.keys()),
            "metrics": trained,
            "sample_count": len(X),
        }

    def predict(
        self,
        symbol: str,
        timeframe: str,
        features: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Soft-voting ensemble prediction.
        Loads all available model files for symbol+timeframe, weights by accuracy.
        Returns {"direction", "score", "buy_pct", "sell_pct", "neutral_pct", "models_used"}.
        """
        x = np.array([[features.get(k, 0.0) for k in ML_FEATURE_NAMES]])
        models_loaded = []

        for mt in self.MODEL_TYPES:
            path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}_{mt}.pkl")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                models_loaded.append((data["model"], mt, data.get("accuracy", 0.5)))
            except Exception as exc:
                log.warning("Failed to load %s model: %s", mt, exc)

        # Fall back to legacy flat model
        if not models_loaded:
            legacy = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
            if os.path.exists(legacy):
                try:
                    with open(legacy, "rb") as f:
                        data = pickle.load(f)
                    models_loaded.append((data["model"], "random_forest", data.get("accuracy", 0.5)))
                except Exception:
                    pass

        if not models_loaded:
            return {"status": "no_model", "direction": "neutral", "score": 50.0,
                    "buy_pct": 0.0, "sell_pct": 0.0, "neutral_pct": 100.0, "models_used": 0}

        # Weighted soft-vote
        buy_w = sell_w = neutral_w = total_w = 0.0

        for model, mt, acc in models_loaded:
            w = max(0.1, float(acc))
            try:
                proba = model.predict_proba(x)[0]
                classes = [int(c) for c in model.classes_]
                prob_map = dict(zip(classes, proba))

                if mt == "xgboost":
                    # XGBoost was trained with label +1 offset
                    buy_p     = float(prob_map.get(2, 0.0))
                    neutral_p = float(prob_map.get(1, 0.0))
                    sell_p    = float(prob_map.get(0, 0.0))
                else:
                    buy_p     = float(prob_map.get(1, 0.0))
                    sell_p    = float(prob_map.get(-1, 0.0))
                    neutral_p = float(prob_map.get(0, 0.0))

                buy_w     += buy_p     * w
                sell_w    += sell_p    * w
                neutral_w += neutral_p * w
                total_w   += w
            except Exception as exc:
                log.debug("Predict error for %s: %s", mt, exc)

        if total_w == 0:
            return {"status": "error", "direction": "neutral", "score": 50.0,
                    "buy_pct": 0.0, "sell_pct": 0.0, "neutral_pct": 100.0, "models_used": 0}

        buy_pct     = round(buy_w     / total_w * 100, 1)
        sell_pct    = round(sell_w    / total_w * 100, 1)
        neutral_pct = round(neutral_w / total_w * 100, 1)

        if buy_pct >= sell_pct and buy_pct >= neutral_pct:
            direction = "bullish"
        elif sell_pct >= buy_pct and sell_pct >= neutral_pct:
            direction = "bearish"
        else:
            direction = "neutral"

        score = round(50 + (buy_pct - sell_pct) / 2, 1)

        return {
            "status": "ok",
            "direction": direction,
            "score": min(100.0, max(0.0, score)),
            "buy_pct": buy_pct,
            "sell_pct": sell_pct,
            "neutral_pct": neutral_pct,
            "models_used": len(models_loaded),
            "confidence": round(max(buy_pct, sell_pct, neutral_pct), 1),
        }


ensemble_trainer = EnsembleTrainer()
