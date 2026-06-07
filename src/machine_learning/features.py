"""
Feature engineering pipeline for ML models.
Produces a flat feature vector from OHLCV candles + optional supplementary scores.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.indicators.calculator import calculator as ind_calc


class FeatureEngineer:
    def build_features(
        self,
        candles: List[Dict[str, Any]],
        smc_score: Optional[float] = None,
        news_score: Optional[float] = None,
        economic_score: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Build a feature vector from the most recent candles.
        Returns a flat dict {feature_name: float}.
        """
        if len(candles) < 30:
            return {}

        indicators = ind_calc.compute_all(candles)

        close = float(candles[-1]["close"])
        open_ = float(candles[-1]["open"])
        high = float(candles[-1]["high"])
        low = float(candles[-1]["low"])
        volume = float(candles[-1].get("volume") or 0)

        features: Dict[str, float] = {}

        # Price action features
        features["close"] = close
        features["candle_body"] = abs(close - open_)
        features["candle_range"] = high - low
        features["upper_shadow"] = high - max(open_, close)
        features["lower_shadow"] = min(open_, close) - low
        features["is_bullish"] = 1.0 if close > open_ else 0.0

        # Returns
        if len(candles) >= 2:
            prev_close = float(candles[-2]["close"])
            features["return_1"] = (close - prev_close) / prev_close if prev_close else 0.0
        if len(candles) >= 5:
            c5 = float(candles[-5]["close"])
            features["return_5"] = (close - c5) / c5 if c5 else 0.0
        if len(candles) >= 10:
            c10 = float(candles[-10]["close"])
            features["return_10"] = (close - c10) / c10 if c10 else 0.0

        # Indicators
        for key in ["EMA_20", "EMA_50", "EMA_100", "EMA_200"]:
            val = indicators.get(key)
            if val is not None:
                features[f"{key}_dist"] = (close - val) / close if close else 0.0

        for key in ["RSI_14", "STOCH_K", "STOCH_D", "ADX", "PLUS_DI", "MINUS_DI"]:
            val = indicators.get(key)
            if val is not None:
                features[key] = val

        for key in ["MACD_line", "MACD_signal", "MACD_hist"]:
            val = indicators.get(key)
            if val is not None:
                features[key] = val

        atr = indicators.get("ATR_14")
        if atr is not None and close:
            features["ATR_pct"] = atr / close

        bb_upper = indicators.get("BB_upper")
        bb_lower = indicators.get("BB_lower")
        bb_bw = indicators.get("BB_bandwidth")
        if bb_upper is not None and bb_lower is not None and (bb_upper - bb_lower) > 0:
            features["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower)
        if bb_bw is not None:
            features["bb_bandwidth"] = bb_bw

        obv = indicators.get("OBV")
        if obv is not None:
            features["obv_normalized"] = obv / (abs(obv) + 1e-9)

        # External scores
        if smc_score is not None:
            features["smc_score"] = smc_score
        if news_score is not None:
            features["news_score"] = news_score
        if economic_score is not None:
            features["economic_score"] = economic_score

        # Volume relative to recent average
        if len(candles) >= 20:
            avg_vol = sum(float(c.get("volume") or 0) for c in candles[-20:]) / 20
            if avg_vol > 0:
                features["volume_ratio"] = volume / avg_vol

        return {k: float(v) for k, v in features.items() if v is not None}

    def build_dataset(
        self,
        candles: List[Dict[str, Any]],
        lookahead: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Build a labelled dataset from a candle series.
        Label: 1 (price rises in `lookahead` bars), 0 (falls), 2 (flat < 0.1%)
        """
        dataset = []
        min_history = 30
        for i in range(min_history, len(candles) - lookahead):
            window = candles[:i + 1]
            features = self.build_features(window)
            if not features:
                continue
            current_close = float(candles[i]["close"])
            future_close = float(candles[i + lookahead]["close"])
            change_pct = (future_close - current_close) / current_close if current_close else 0
            if change_pct > 0.001:
                label = 1  # BUY
            elif change_pct < -0.001:
                label = 0  # SELL
            else:
                label = 2  # NEUTRAL
            dataset.append({"features": features, "label": label})
        return dataset


feature_engineer = FeatureEngineer()
