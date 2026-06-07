"""
ML model trainer — trains XGBoost, LightGBM, CatBoost ensemble.
Models are serialized to disk and versioned.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("ML_MODEL_DIR", "models")


def _ensure_dir() -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)


class MLTrainer:
    def train(
        self,
        dataset: List[Dict[str, Any]],
        model_name: str = "ensemble",
    ) -> Dict[str, Any]:
        """
        Train XGBoost + LightGBM + CatBoost on the dataset.
        Falls back gracefully if any library is unavailable.
        Returns: {"version": str, "metrics": dict, "models": list}
        """
        if len(dataset) < 50:
            return {"error": "Insufficient data for training (need ≥50 samples)"}

        X = []
        y = []
        feature_names: Optional[List[str]] = None

        for row in dataset:
            feats = row["features"]
            if feature_names is None:
                feature_names = list(feats.keys())
            X.append([feats.get(f, 0.0) for f in feature_names])
            y.append(row["label"])

        _ensure_dir()
        version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        trained_models = []
        metrics: Dict[str, Any] = {}

        # Train each model
        for model_type in ["xgboost", "lightgbm", "catboost"]:
            model, model_metrics = self._train_single(model_type, X, y)
            if model is not None:
                path = os.path.join(MODEL_DIR, f"{model_name}_{model_type}_{version}.pkl")
                with open(path, "wb") as f:
                    pickle.dump({"model": model, "feature_names": feature_names, "version": version}, f)
                trained_models.append(model_type)
                metrics[model_type] = model_metrics
                log.info("Trained %s — accuracy: %.3f", model_type, model_metrics.get("accuracy", 0))

        # Save metadata
        meta_path = os.path.join(MODEL_DIR, f"{model_name}_meta_{version}.json")
        with open(meta_path, "w") as f:
            json.dump({
                "version": version,
                "model_name": model_name,
                "trained_models": trained_models,
                "metrics": metrics,
                "feature_names": feature_names,
                "sample_count": len(X),
                "created_at": datetime.utcnow().isoformat(),
            }, f)

        return {
            "version": version,
            "trained_models": trained_models,
            "metrics": metrics,
            "sample_count": len(X),
        }

    def _train_single(
        self, model_type: str, X: List[List[float]], y: List[int]
    ) -> Tuple[Any, Dict[str, float]]:
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        model = None
        try:
            if model_type == "xgboost":
                from xgboost import XGBClassifier
                model = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, use_label_encoder=False, eval_metric="mlogloss", verbosity=0)
                model.fit(X_train, y_train)
            elif model_type == "lightgbm":
                from lightgbm import LGBMClassifier
                model = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, verbose=-1)
                model.fit(X_train, y_train)
            elif model_type == "catboost":
                from catboost import CatBoostClassifier
                model = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.1, verbose=0)
                model.fit(X_train, y_train)
        except ImportError:
            log.warning("%s not installed — skipping", model_type)
            return None, {}
        except Exception:
            log.exception("Failed to train %s", model_type)
            return None, {}

        if model is None:
            return None, {}

        y_pred = model.predict(X_test)
        accuracy = sum(p == t for p, t in zip(y_pred, y_test)) / len(y_test) if y_test else 0
        return model, {"accuracy": round(float(accuracy), 4)}


ml_trainer = MLTrainer()
