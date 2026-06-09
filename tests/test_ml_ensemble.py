"""Unit tests for ML ensemble trainer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import random
import tempfile
import pytest
from core.constants import ML_FEATURE_NAMES
from ml.ensemble import EnsembleTrainer, walk_forward_accuracy
from sklearn.ensemble import RandomForestClassifier


def _make_dataset(n: int = 200, seed: int = 42) -> list:
    random.seed(seed)
    rows = []
    for _ in range(n):
        feats = {k: random.gauss(0, 1) for k in ML_FEATURE_NAMES}
        label = 1 if feats.get("rsi", 0) > 0 else -1
        rows.append({"features": feats, "label": label})
    return rows


@pytest.fixture
def tmp_model_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ML_MODEL_DIR", str(tmp_path))
    # Patch config to use tmp_path
    from config import settings
    settings.ML_MODEL_DIR = str(tmp_path)
    return tmp_path


class TestMLFeatureNames:
    def test_no_duplicates(self):
        assert len(ML_FEATURE_NAMES) == len(set(ML_FEATURE_NAMES))

    def test_expected_features_present(self):
        required = ["rsi", "macd", "atr_pct", "smc_score"]
        for f in required:
            assert f in ML_FEATURE_NAMES, f"Missing feature: {f}"

    def test_count(self):
        assert len(ML_FEATURE_NAMES) == 14


class TestWalkForwardAccuracy:
    def test_returns_float(self):
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        X = [[i, i * 2] for i in range(100)]
        y = [i % 2 for i in range(100)]
        acc = walk_forward_accuracy(model, X, y, n_splits=3)
        assert isinstance(acc, float)
        assert 0.0 <= acc <= 1.0

    def test_insufficient_data_returns_zero(self):
        model = RandomForestClassifier(n_estimators=5)
        X = [[i] for i in range(5)]
        y = [0] * 5
        acc = walk_forward_accuracy(model, X, y)
        assert acc == 0.0


class TestEnsembleTrainer:
    def test_train_returns_ok(self, tmp_model_dir):
        trainer = EnsembleTrainer()
        dataset = _make_dataset(200)
        result = trainer.train(dataset, "XAUUSD", "60")
        assert result["status"] == "ok"
        assert "random_forest" in result["trained_models"]
        assert result["sample_count"] == 200

    def test_train_insufficient_data(self, tmp_model_dir):
        trainer = EnsembleTrainer()
        dataset = _make_dataset(10)
        result = trainer.train(dataset, "XAUUSD", "60")
        assert result["status"] == "error"

    def test_predict_no_model_returns_no_model(self, tmp_model_dir):
        trainer = EnsembleTrainer()
        feats = {k: 0.5 for k in ML_FEATURE_NAMES}
        result = trainer.predict("BTCUSD", "999", feats)
        assert result["status"] == "no_model"

    def test_predict_after_train(self, tmp_model_dir):
        trainer = EnsembleTrainer()
        dataset = _make_dataset(200)
        trainer.train(dataset, "XAUUSD", "60")
        feats = {k: 0.5 for k in ML_FEATURE_NAMES}
        result = trainer.predict("XAUUSD", "60", feats)
        assert result["status"] == "ok"
        assert result["direction"] in {"bullish", "bearish", "neutral"}
        assert 0 <= result["score"] <= 100
        assert result["models_used"] >= 1

    def test_predict_probabilities_sum_to_100(self, tmp_model_dir):
        trainer = EnsembleTrainer()
        dataset = _make_dataset(200)
        trainer.train(dataset, "XAUUSD", "60")
        feats = {k: 0.5 for k in ML_FEATURE_NAMES}
        result = trainer.predict("XAUUSD", "60", feats)
        total = result["buy_pct"] + result["sell_pct"] + result["neutral_pct"]
        assert abs(total - 100.0) < 1.0, f"Probabilities sum to {total}"
