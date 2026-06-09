# Before / After Comparison — Signal System Fix

**Date:** 2026-06-09  
**Market:** XAUUSD H1, session ~12:30–13:07 UTC  
**Conditions:** H4/H1/M15 all bullish EMA alignment, SMC=100, economic_score=80

---

## Signal Output Comparison

| Field | BEFORE (buggy) | AFTER (fixed) |
|-------|----------------|---------------|
| `signal_type` | **`"NO TRADE"`** | **`"BUY"`** |
| `combined_score` | 61.7 | 62.0 |
| `composite_score` | **40.0** | **70.0** |
| `confluence.alignment` | **`"conflict"`** | **`"full"`** |
| `confluence.h4_direction` | `"bullish"` | `"bullish"` (unchanged) |
| `confluence.h1_direction` | `"bullish"` | `"bullish"` (unchanged) |
| `confluence.m15_direction` | `"bullish"` | `"bullish"` (unchanged) |
| `conf_dir` (internal) | `"bearish"` | `"bullish"` |
| `entry` | N/A | 4339.28 |
| `stop_loss` | N/A | 4330.04 |
| `take_profit` | N/A | 4350.28 |
| `rr` | N/A | 1.19 |
| `lot_size` | N/A | 0.11 |
| `risk_amount_usd` | N/A | $100.00 |

---

## Bug Analysis: What Changed

### Bug RC-1: Key Mismatch (`composite_score` vs `combined_score`)

**Before** (`backend/routers/signals.py` lines 89–96):
```python
conf_dir = "bullish" if result.get("composite_score", 50) > 50 else "bearish"
#                                   ^^^^^^^^^^^^^^^ KEY MISSING IN RESULT
# 50 > 50 = False → conf_dir = "bearish" (WRONG — market is all-bullish)

composite = float(result.get("composite_score", 50.0))
#                             ^^^^^^^^^^^^^^^ KEY MISSING → always 50.0
```

**After**:
```python
combined = float(result.get("combined_score", 50.0))
#                             ^^^^^^^^^^^^^^ CORRECT KEY → 62.0
conf_dir = "bullish" if combined > 50 else "bearish"
# 62.0 > 50 = True → conf_dir = "bullish" (CORRECT)

composite = combined  # starts from actual score
```

### Bug RC-2: NEUTRAL → BUY Upgrade Missing

**Before**: `_apply_confluence()` could only downgrade (NEUTRAL → NO TRADE on conflict) but never upgrade (NEUTRAL → BUY when confluence bonus crossed threshold).

**After**: Added upgrade logic — when confluence bonus pushes composite ≥ 62 (BUY threshold), signal is upgraded to BUY with freshly computed SL/TP/RR:
```python
if result.get("signal_type") == "NEUTRAL" and result.get("entry"):
    atr = _calc_atr(candles_h1)
    entry = float(result["entry"])
    if composite >= _s.SIGNAL_BUY_THRESHOLD:
        sl, tp1, tp2, tp3 = _compute_sl_tp("BUY", entry, candles_h1, atr)
        rr = round(abs(tp2 - entry) / (abs(entry - sl) + 1e-9), 2) if sl and tp2 else None
        conf = round(min(abs(composite - 50) * 3.33, 100), 1)
        result.update({"signal_type": "BUY", "stop_loss": sl,
                       "take_profit": tp2, "tp1": tp1, "tp3": tp3,
                       "rr": rr, "confidence": conf})
```

### Infrastructure Fix: `.dockerignore` and Volume Path

**Before**: `.dockerignore` had `models/` which excluded `backend/models/` (Python ORM models) from the build context. A Docker volume mounted at `/app/models` was overriding the Python models with stale files from the volume.

**After**: 
- Removed `models/` from `.dockerignore`
- Moved ML pkl volume mount from `/app/models` → `/app/ml_models`
- Updated `ML_MODEL_DIR` from `/app/models` → `/app/ml_models` in `config.py` and `docker-compose.yml`
- Result: Python models are now correctly included in the image, ML pkl files persist in a separate volume

---

## Causal Chain (Before → After)

**Before (bug state):**
```
combined_score=61.7 → NEUTRAL (< 62 threshold)
    ↓
_apply_confluence():
    composite_score key missing → defaults to 50.0
    50 > 50 = False → conf_dir = "bearish"
    H4=bullish + conf_dir=bearish → alignment = "conflict"
    composite = 50.0 - 10 = 40.0
    40.0 < 70 → signal_type = "NO TRADE"
    ↓
Output: NO TRADE (WRONG — all TFs bullish)
```

**After (fixed state):**
```
combined_score=62.0 → BUY (>= 62 threshold, slight RSI tick up)
    ↓
_apply_confluence():
    combined_score key → 62.0
    62.0 > 50 = True → conf_dir = "bullish"
    H4=bullish + conf_dir=bullish → alignment = "full"
    composite = 62.0 + 8 = 70.0
    signal_type stays "BUY"
    ↓
Output: BUY, Entry=4339.28, SL=4330.04, TP=4350.28, Lots=0.11
```

---

## DB History: All 20 Previous Signals

**Before fix:** All 20 signals in DB = "NO TRADE"  
**After fix:** New signals correctly generated as BUY/SELL/NEUTRAL based on market conditions

Signal ID 57 is the first correctly generated BUY signal.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/routers/signals.py` | Fixed `composite_score` → `combined_score` (×2), added NEUTRAL→BUY/SELL upgrade logic |
| `backend/config.py` | `ML_MODEL_DIR` `/app/models` → `/app/ml_models` |
| `backend/Dockerfile` | `mkdir /app/models` → `mkdir /app/ml_models` |
| `docker-compose.yml` | Volume mount `models_data:/app/models` → `models_data:/app/ml_models`, `ML_MODEL_DIR` updated |
| `.dockerignore` | Removed `models/` exclusion that was blocking `backend/models/` from build |
| `.env` | `DATABASE_URL` updated to match actual Postgres credentials |
