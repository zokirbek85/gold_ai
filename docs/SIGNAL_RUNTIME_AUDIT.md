# Signal Runtime Audit — Phase 1 & 2 Findings

**Date:** 2026-06-09  
**Investigator:** Live diagnostic — all data from running Docker containers and source code  
**Environment:** docker compose (backend:8001, db:5432, redis:6379, frontend:3000)

---

## 1. Environment State

| Component | Status | Details |
|-----------|--------|---------|
| backend | healthy (8h) | port 8001, image rebuilt 2026-06-09 |
| db (postgres) | healthy | goldai DB, port 5432 |
| redis | healthy | port 6379 |
| frontend | healthy | port 3000 |
| Twelvedata API | active | key confirmed via live fetch |
| ML model | loaded | `/app/models/xauusd_60.pkl` — 1.5 MB, trained today 12:13 |

---

## 2. Live Signal Snapshot (captured 2026-06-09 12:30)

```json
{
  "signal_type": "NO TRADE",
  "combined_score": 61.7,
  "composite_score": 40.0,
  "technical_score": 42.9,
  "smc_score": 100.0,
  "ml_score": 44.1,
  "news_score": 48.2,
  "economic_score": 80.0,
  "confluence": {
    "alignment": "conflict",
    "h4_direction": "bullish",
    "h1_direction": "bullish",
    "m15_direction": "bullish"
  }
}
```

**Red flag**: All three timeframes report BULLISH yet alignment = "conflict". Confirmed false positive. All 20 historical signals in the DB are "NO TRADE".

---

## 3. Root Cause Analysis

### RC-1 (CRITICAL): Key Mismatch in `_apply_confluence()`

**File:** `backend/routers/signals.py` lines 89–96  
**Symptom:** `composite_score=40.0` while `combined_score=61.7`; alignment="conflict" on all-bullish market

`generate_signal()` returns the key `"combined_score"` (signal_service.py:271):
```python
return {"combined_score": combined, ...}  # key is combined_score
```

`_apply_confluence()` reads the non-existent key `"composite_score"`:
```python
# LINE 89 — WRONG KEY:
conf_dir = "bullish" if result.get("composite_score", 50) > 50 else "bearish"
# 50 > 50 = False → conf_dir always "bearish" on NEUTRAL signals

# LINE 96 — WRONG KEY:
composite = float(result.get("composite_score", 50.0))
# composite always = 50.0 regardless of actual score
```

**Causal chain:**
1. `combined_score=61.7` → signal_type="NEUTRAL" (below 62 threshold by 0.3)
2. `_apply_confluence()` reads `composite_score` → KeyError → defaults to 50.0
3. `50 > 50 = False` → `conf_dir = "bearish"`
4. H4 bullish + conf_dir bearish → `alignment = "conflict"`
5. `composite = 50.0 - 10 = 40.0`
6. `40.0 < 70` → `signal_type = "NO TRADE"`

**Live proof (reproduced in container):**
```
composite_score key exists: False
combined_score key exists:  True
composite (reads composite_score): 50.0
conf_dir determined: bearish
50 > 50 = False

CORRECT BEHAVIOR (after fix):
composite (reads combined_score): 61.7
conf_dir: bullish
61.7 > 50 = True
```

### RC-2: Confluence Cannot Upgrade NEUTRAL → BUY

**File:** `backend/routers/signals.py` lines 97–113  
**Symptom:** After fixing RC-1, composite=69.7 (≥ 62 BUY threshold) but signal_type stays "NEUTRAL"

`_apply_confluence()` can only DOWNGRADE (→ NO TRADE on conflict) but never UPGRADES a NEUTRAL signal even when the confluence bonus pushes composite past the BUY threshold:

```python
# With fix: composite = 61.7 + 8 = 69.7 (full alignment bonus)
# 69.7 >= 62.0 (BUY threshold) — should generate BUY signal
# BUT: code only touches signal_type in the 'else' (conflict) branch
# NEUTRAL stays NEUTRAL despite composite = 69.7
```

**Expected result after full fix:**
- RC-1 fix → conf_dir="bullish", alignment="full", composite=69.7
- RC-2 fix → 69.7 ≥ 62.0 → signal_type upgraded to "BUY" with SL/TP computed

### RC-3 (MINOR): Economic Calendar Direction Hardcoded Neutral

**File:** `backend/services/calendar_service.py` line ~173  
```python
"direction": "neutral"  # hardcoded, never changes
```
Economic score contributes to combined_score correctly (10% weight) but direction context is always "neutral". Does not cause NO TRADE but reduces diagnostic value.

### RC-4 (INFORMATIONAL): ML Accuracy 51%

**File:** `/app/models/xauusd_60.pkl`  
`n_features_in_=14`, `accuracy=0.5099`. Training and inference use the same `ML_FEATURE_NAMES` (14 features) — no code mismatch. Low accuracy is a data/market issue, not a bug. Meta JSON showing 20 legacy features is from an old training run and does not reflect current code.

---

## 4. Signal Score Breakdown (Live)

| Component | Weight | Score | Contribution |
|-----------|--------|-------|--------------|
| Technical | 35% | 42.9 | 15.0 |
| SMC | 25% | 100.0 | 25.0 |
| ML | 20% | 44.1 | 8.8 |
| News | 10% | 48.2 | 4.8 |
| Economic | 10% | 80.0 | 8.0 |
| **Combined** | | | **61.7** |

BUY threshold = 62.0 — combined_score misses by **0.3 points**.  
With full alignment bonus (+8): composite = **69.7** → above BUY threshold.

---

## 5. Impact Assessment

| Bug | Signals Affected | Severity |
|-----|-----------------|----------|
| RC-1: key mismatch | ALL signals (100%) | Critical |
| RC-2: no NEUTRAL upgrade | All NEUTRAL signals near threshold | High |
| RC-3: calendar hardcoded | Informational only | Low |
| RC-4: ML accuracy 51% | ML component only (20% weight) | Low |

**All 20 signals in DB are "NO TRADE"** — caused entirely by RC-1.

---

## 6. Fix Plan

1. `backend/routers/signals.py` lines 89, 96: `composite_score` → `combined_score`
2. `backend/routers/signals.py` `_apply_confluence()`: add upgrade logic (NEUTRAL → BUY/SELL) when composite crosses threshold after confluence adjustment, with SL/TP re-computation from H1 candles
3. Optional: fix calendar_service.py direction logic

See `FINAL_SIGNAL_DIAGNOSIS.md` for before/after comparison and validation results.
