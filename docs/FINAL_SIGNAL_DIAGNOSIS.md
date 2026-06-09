# Final Signal Diagnosis — Gold AI XAUUSD Signal System

**Investigation Period:** 2026-06-09  
**Investigator:** Live diagnostic — running containers, source code, DB queries, live API calls  
**Status:** All critical bugs FIXED and VALIDATED

---

## Executive Summary

The signal system was generating "NO TRADE" on every signal (100% of 20 historical signals in DB), even when all three timeframes (H4/H1/M15) showed bullish alignment. Root cause: a single incorrect dictionary key in `_apply_confluence()` caused the confluence engine to always start with `composite=50.0` and determine `conf_dir="bearish"`, creating a false conflict with bullish market data.

A secondary infrastructure bug (`.dockerignore` excluding Python ORM models from Docker image, overridden by a stale volume) prevented the fixed code from reaching the running container.

Both issues are now fixed. The live system generates BUY/SELL signals correctly as of 13:07 UTC 2026-06-09.

---

## Root Causes (Ranked by Impact)

### #1 — Key Mismatch: `composite_score` vs `combined_score` [CRITICAL]

| | Value |
|-|-------|
| **File** | `backend/routers/signals.py:89,96` |
| **Impact** | 100% of signals → NO TRADE |
| **Fix** | 2-line change: `composite_score` → `combined_score` |

`generate_signal()` returns `"combined_score"` but `_apply_confluence()` read `"composite_score"` (non-existent key). Default of 50 caused:
- `50 > 50 = False` → `conf_dir = "bearish"` on all NEUTRAL signals
- Confluence compared bearish direction against bullish TFs → always "conflict"
- -10 penalty on already-wrong 50.0 → `composite=40.0 < 70` → force NO TRADE

### #2 — NEUTRAL → BUY Upgrade Missing [HIGH]

| | Value |
|-|-------|
| **File** | `backend/routers/signals.py:_apply_confluence()` |
| **Impact** | Signals near threshold (within 8 points of 62) stayed NEUTRAL |
| **Fix** | Added upgrade logic with SL/TP/confidence recomputation |

`_apply_confluence()` could only downgrade (conflict → NO TRADE) but never upgrade (NEUTRAL → BUY when confluence bonus pushes composite ≥ 62). With combined=61.7 and full alignment bonus +8=69.7, the signal should have been BUY.

### #3 — `.dockerignore` Blocked Python Models [HIGH, infrastructure]

| | Value |
|-|-------|
| **File** | `.dockerignore`, `docker-compose.yml` |
| **Impact** | Fixes to `backend/models/signal.py` never reached the running container |
| **Fix** | Removed `models/` from `.dockerignore`; moved ML pkl volume to `/app/ml_models` |

`models/` in `.dockerignore` excluded `backend/models/` from Docker build context. A volume mounted at `/app/models` persisted old Python ORM model files, overriding every image rebuild.

### #4 — ML Accuracy 51% [LOW, not a bug]

ML model trained on 213 samples, accuracy 50.99%. Training and inference both use the correct 14 `ML_FEATURE_NAMES`. Low accuracy is a data quality issue (small sample, ranging market), not a code bug. The model contributes 20% weight and is a minor drag on combined_score.

### #5 — Economic Calendar Direction Hardcoded [LOW]

| | Value |
|-|-------|
| **File** | `backend/services/calendar_service.py:~173` |
| **Impact** | Economic direction always "neutral" regardless of events |
| **Status** | Not fixed — directional context is informational only; score (10% weight) still correct |

---

## Validation Results

### Live Signal Before Fix
```json
{
  "signal_type": "NO TRADE",
  "combined_score": 61.7,
  "composite_score": 40.0,
  "confluence": {"alignment": "conflict", "h4_direction": "bullish", ...}
}
```

### Live Signal After Fix (ID=57, 13:07:30 UTC)
```json
{
  "signal_type": "BUY",
  "combined_score": 62.0,
  "composite_score": 70.0,
  "confluence": {"alignment": "full", "score": 80.0, "h4_direction": "bullish", ...},
  "entry": 4339.2812,
  "stop_loss": 4330.0397,
  "take_profit": 4350.2849,
  "lot_size": 0.11,
  "risk_amount_usd": 100.0,
  "rr": 1.19
}
```

---

## Complete Fix Summary

| File | Change | Reason |
|------|--------|--------|
| `backend/routers/signals.py` | `composite_score` → `combined_score` (×2) | RC-1: wrong key |
| `backend/routers/signals.py` | Added NEUTRAL→BUY/SELL upgrade in `_apply_confluence()` | RC-2: missing upgrade path |
| `.dockerignore` | Removed `models/` entry | RC-3: was excluding Python ORM models |
| `docker-compose.yml` | Volume mount `/app/models` → `/app/ml_models` | RC-3: separate pkl storage from code |
| `backend/config.py` | `ML_MODEL_DIR` `/app/models` → `/app/ml_models` | RC-3: consistent path |
| `backend/Dockerfile` | `mkdir /app/models` → `mkdir /app/ml_models` | RC-3: consistent path |
| `.env` | `DATABASE_URL` updated to `goldai:goldai_dev_password` | DB auth failure after volume recreate |

---

## Remaining Recommended Work

1. **Retrain ML model** — trigger `POST /api/v1/ml/train` to get a fresh model in the new `/app/ml_models/` directory. Current model is in the old volume path.
2. **Fix calendar direction** — `calendar_service.get_aggregate_score()` always returns `"direction": "neutral"`.
3. **RSI dead zone (45–55)** — currently contributes 0 signal. A small ±5 score for RSI 45–55 would reduce volatility in combined_score near the BUY/SELL threshold.
4. **Monitor signal quality** — with the fix in place, run for 24–48 hours and compare signal distribution (% BUY vs SELL vs NEUTRAL) against expected market conditions.

---

## System State (Post-Fix)

| Component | State |
|-----------|-------|
| Backend | healthy, port 8001 |
| Signal generation | BUY/SELL/NEUTRAL correctly assigned |
| Confluence engine | Correctly reads combined_score, full/partial/conflict alignments working |
| ML model | needs retrain (old pkl in stale volume path) |
| DB enrichment columns | Added via ALTER TABLE |
| Docker image | Correctly includes all updated Python models |
| ML pkl volume | Now mounted at `/app/ml_models` (separated from code) |
