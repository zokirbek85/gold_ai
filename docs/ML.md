# Gold AI — Machine Learning

## Overview

Gold AI uses a multi-model ensemble for direction prediction (bullish / neutral / bearish) on XAUUSD. The ensemble is trained on historical candle data and evaluated via walk-forward cross-validation to prevent look-ahead bias.

## Feature Set

14 features, defined in `backend/core/constants.py:ML_FEATURE_NAMES`:

| Feature         | Description                              |
|-----------------|------------------------------------------|
| rsi             | 14-period RSI (0–100)                    |
| macd            | MACD line value                          |
| macd_signal     | MACD signal line                         |
| macd_hist       | MACD histogram                           |
| ema_20_dist     | % distance from 20-period EMA           |
| ema_50_dist     | % distance from 50-period EMA           |
| ema_200_dist    | % distance from 200-period EMA          |
| atr_pct         | ATR as % of close price                  |
| bb_position     | Position within Bollinger Bands (0–1)    |
| candle_body_ratio | Body / total range (0–1)              |
| upper_wick_ratio | Upper wick / total range               |
| lower_wick_ratio | Lower wick / total range               |
| volume_ratio    | Volume / 20-period average volume        |
| smc_score       | SMC composite score (0–100)              |

## Labels

| Label | Value | Meaning                      |
|-------|-------|------------------------------|
| -1    | bearish | Price fell next period     |
| 0     | neutral | Price moved < threshold    |
| 1     | bullish | Price rose next period     |

## Ensemble Architecture

`backend/ml/ensemble.py`:

```
Training data → walk_forward_accuracy() per model
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼              ▼
     RandomForest    XGBoost       LightGBM       CatBoost
     (always)        (optional)    (optional)     (optional)
            │              │              │              │
            └──────────────┴──────────────┴──────────────┘
                                  │
                     Soft voting (weighted by WF accuracy)
                                  │
                          direction + score
```

Models are saved as `{symbol}_{timeframe}_{model_type}.pkl` in `ML_MODEL_DIR`.

## Walk-Forward Validation

`walk_forward_accuracy(model, X, y, n_splits=5)`:

- Uses `TimeSeriesSplit` — no data leakage
- Returns mean accuracy across folds
- Models with insufficient data (< 50 samples per fold) return `0.0`
- Minimum training size: 100 samples total; soft vote excludes 0.0-accuracy models

## Training

Training is triggered:
1. **Manually** via `POST /api/v1/ml/train`
2. **Automatically** by the ML feedback loop (when error rate threshold is exceeded)
3. **Via Telegram** with `/retrain` command

Minimum training dataset: 100 samples. Recommended: 500+.

## Feedback Loop

`src/machine_learning/feedback_models.py` stores each prediction's outcome:

1. At signal generation: save `predicted_dir`, `confidence`, `features_snapshot`
2. After N candles: resolve actual direction, update `was_correct`, `actual_dir`
3. `GET /api/v1/ml/feedback/accuracy` — accuracy by session, by timeframe
4. `GET /api/v1/ml/feedback/error-patterns` — recurring failure patterns
5. Auto-retrain triggers when: error_rate > 40% AND at least 200 new candles since last train

## Prediction API

```
POST /api/v1/ml/predict
{
  "symbol": "XAUUSD",
  "timeframe": "60"
}

Response:
{
  "status": "ok",
  "direction": "bullish",
  "score": 72.5,
  "buy_pct": 72.5,
  "sell_pct": 18.0,
  "neutral_pct": 9.5,
  "models_used": 3,
  "model_available": true
}
```

## Configuration

| Setting      | Env Var              | Default   |
|--------------|----------------------|-----------|
| Model storage| ML_MODEL_DIR         | /app/models |
| Min confidence for Telegram | SIGNAL_MIN_CONFIDENCE | 65.0 |

## Adding a New Model

1. Install the library in `backend/requirements.txt`
2. Add to `EnsembleTrainer._train_single()` in `backend/ml/ensemble.py`
3. Handle import errors with `try/except ImportError`
4. Model is automatically included in walk-forward evaluation
