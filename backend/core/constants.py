"""
Single source of truth for shared constants.
Avoids FEATURE_NAMES being duplicated across ml_service, signal_service, trainer.
"""
from __future__ import annotations

ML_FEATURE_NAMES: list[str] = [
    "rsi", "macd", "macd_signal", "macd_hist",
    "ema_20_dist", "ema_50_dist", "ema_200_dist",
    "atr_pct", "bb_position",
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "volume_ratio", "smc_score",
]

# Signal scoring weights
W_TECHNICAL: float = 0.35
W_SMC: float = 0.25
W_ML: float = 0.20
W_NEWS: float = 0.10
W_ECONOMIC: float = 0.10
