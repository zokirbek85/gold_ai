# SIGNAL DEBUG REPORT — Gold AI
_Generated: 2026-06-09_

---

## TL;DR — Why Signals Keep Returning NO TRADE / NEUTRAL

There are **5 compounding root causes**, not one. They all push the composite score toward 50 simultaneously:

| # | Root Cause | Impact | File |
|---|------------|--------|------|
| 1 | No trained ML model → `ml_score = 50.0` (neutral, no contribution) | Always blocks directional push | `signal_service.py:177` |
| 2 | H4 conflict penalty: `-10` to composite + hard NO TRADE if `composite < 70` | Kills borderline signals | `routers/signals.py:101-113` |
| 3 | RSI 45–55 contributes **zero points** to bull or bear | Tech score stuck near 50 | `signal_service.py:131-138` |
| 4 | Economic score direction is **permanently hardcoded to `"neutral"`** | Econ layer never aids direction | `calendar_service.py:173` |
| 5 | News direction requires **>55% same-sentiment** to escape neutral | Mixed-headline markets stay neutral | `news_service.py:194-197` |

---

## Full Decision Path

```
POST /api/v1/signals/generate
        │
        ├─1─ fetch_and_store() ─── pulls H1 candles from Twelvedata (or DB)
        │
        ├─2─ refresh_news() + refresh_calendar() ─── updates DB
        │
        ├─3─ get_sentiment_summary() ─── news_score: float, news_dir: str
        │      └─ if no news in DB → score=50.0, direction="neutral"
        │      └─ if mixed news   → score varies, direction="neutral" (needs >55% same)
        │
        ├─4─ get_aggregate_score() ─── econ_score: float
        │      └─ direction is ALWAYS "neutral" (hardcoded, line 173 calendar_service.py)
        │      └─ score = 50 + high_usd_events * 5  (max 100)
        │
        ├─5─ generate_signal(candles, ...) ─── signal_service.py
        │
        │      ├─ _technical_score(snap, candles)
        │      │    RSI < 30        → bull += 30
        │      │    RSI 30–44       → bull += 15
        │      │    RSI > 70        → bear += 30
        │      │    RSI 55–70       → bear += 15
        │      │    RSI 45–55       → ZERO (neither)   ← ⚠ kills signal in neutral markets
        │      │    MACD > signal   → bull += 25
        │      │    MACD < signal   → bear += 25
        │      │    MACD > 0        → bull += 5
        │      │    MACD < 0        → bear += 5
        │      │    close > EMA200  → bull += 25
        │      │    close < EMA200  → bear += 25
        │      │    below BB lower  → bull += 15
        │      │    above BB upper  → bear += 15
        │      │    score = bull / (bull + bear) × 100
        │      │
        │      ├─ _smc_score(candles)
        │      │    calls smc_service.score(candles).get("score", 50)
        │      │    returns 0–100 based on OB/FVG/BOS alignment
        │      │
        │      ├─ _ml_score(symbol, timeframe, candles)
        │      │    path = /app/models/xauusd_60.pkl
        │      │    if NOT found → returns 50.0  ← ⚠ most common cause
        │      │    if found → score = 50 + (buy_pct - sell_pct) / 2
        │      │
        │      └─ COMBINE:
        │           combined = 0.35*tech + 0.25*smc + 0.20*ml + 0.10*news + 0.10*econ
        │
        │           BUY  threshold: combined >= 62.0  (SIGNAL_BUY_THRESHOLD)
        │           SELL threshold: combined <= 38.0  (SIGNAL_SELL_THRESHOLD)
        │           else: NEUTRAL
        │
        ├─6─ _apply_confluence() ─── multi-timeframe check (routers/signals.py:77-113)
        │
        │      ├─ fetch H4 (timeframe=240) and M15 (timeframe=15) candles
        │      │
        │      ├─ confluence_score() uses EMA20 vs EMA50 per timeframe:
        │      │    H4  → ema20>ema50 = bullish, else bearish or neutral
        │      │    H1  → ema20>ema50 = bullish, else bearish or neutral
        │      │    M15 → ema20>ema50 = bullish, else bearish or neutral
        │      │
        │      ├─ SCORING:
        │      │    start = 50
        │      │    H4 agrees  → +15
        │      │    H4 opposes → -20   ← ⚠ heaviest weight
        │      │    H1 agrees  → +10
        │      │    M15 agrees → +5
        │      │
        │      ├─ ALIGNMENT LABEL:
        │      │    H4 opposes → "conflict"   ← ⚠ H4 alone sets conflict
        │      │    all agree  → "full"
        │      │    else       → "partial"
        │      │
        │      └─ COMPOSITE ADJUSTMENT:
        │           "full"    → composite += 8
        │           "partial" → composite += 3
        │           "conflict"→ composite -= 10   ← ⚠
        │                       AND if composite < 70:
        │                           signal_type = "NO TRADE"   ← ⚠ hard override
        │                           stop_loss = None
        │                           take_profit = None
        │
        └─7─ enrich_signal(result) ─── signal_service.py:277-354
               if signal_type == "NEUTRAL":
                   plain_explanation = "⚪ NEUTRAL — Market unclear. Do not trade."
               if signal_type == "NO TRADE" (from confluence):
                   → same enrich path as NEUTRAL (entry exists, sl=None → treated as NEUTRAL)
```

---

## Threshold Reference Table

All thresholds currently active:

| Parameter | Value | Location |
|-----------|-------|----------|
| `SIGNAL_BUY_THRESHOLD` | `62.0` | `config.py` + `.env` |
| `SIGNAL_SELL_THRESHOLD` | `38.0` | `config.py` + `.env` |
| `SIGNAL_MIN_CONFIDENCE` | `65.0` | `config.py` (Telegram filter) |
| Confluence conflict threshold | `< 70.0` composite | `routers/signals.py:103` |
| Confluence full bonus | `+8` | `routers/signals.py:98` |
| Confluence partial bonus | `+3` | `routers/signals.py:100` |
| Confluence conflict penalty | `-10` | `routers/signals.py:102` |
| H4 alignment bonus | `+15` | `src/signals/scorer.py:213` |
| H4 opposition penalty | `-20` | `src/signals/scorer.py:216` |
| H1 alignment bonus | `+10` | `src/signals/scorer.py:218` |
| M15 alignment bonus | `+5` | `src/signals/scorer.py:221` |
| News direction threshold | `55%` majority | `news_service.py:194` |
| RSI oversold bull bonus | `+30` (RSI < 30) | `signal_service.py:132` |
| RSI overbought bear bonus | `+30` (RSI > 70) | `signal_service.py:135` |
| RSI mild bull zone | `+15` (RSI < 45) | `signal_service.py:134` |
| RSI mild bear zone | `+15` (RSI > 55) | `signal_service.py:137` |
| RSI neutral deadzone | **0** (45–55) | `signal_service.py:131` |
| MACD crossover bonus | `±25` | `signal_service.py:143-145` |
| MACD absolute sign bonus | `±5` | `signal_service.py:147-148` |
| EMA200 position bonus | `±25` | `signal_service.py:152-155` |
| BB band touch bonus | `±15` | `signal_service.py:160-163` |
| Minimum candles required | `50` | `signal_service.py:215` |
| ML feature count | `14` | `core/constants.py` |
| Technical weight | `0.35 (35%)` | `core/constants.py` |
| SMC weight | `0.25 (25%)` | `core/constants.py` |
| ML weight | `0.20 (20%)` | `core/constants.py` |
| News weight | `0.10 (10%)` | `core/constants.py` |
| Economic weight | `0.10 (10%)` | `core/constants.py` |

---

## Score Simulation: Typical "NO TRADE" Market

Assume: XAUUSD H1, RSI=52, MACD slightly above signal, price above EMA200, no ML model, neutral news, no upcoming USD events.

| Component | Raw score | Weighted |
|-----------|-----------|----------|
| Technical | RSI=52 (0pts) + MACD bull (+25) + above EMA200 (+25) = 50/100 → **66.7** | 0.35 × 66.7 = **23.3** |
| SMC | No clear OB/FVG → **50.0** | 0.25 × 50.0 = **12.5** |
| ML | No model file → **50.0** | 0.20 × 50.0 = **10.0** |
| News | Mixed headlines → **50.0** | 0.10 × 50.0 = **5.0** |
| Economic | Default → **50.0** | 0.10 × 50.0 = **5.0** |
| **Combined** | | **55.8** → NEUTRAL (< 62) |

Even with a moderately bullish technical score (66.7), the system outputs NEUTRAL because:
- ML (20% weight) is anchored at 50 — no trained model
- News and Economic (20% total) provide no directional push
- Combined 55.8 is 6.2 points short of the BUY threshold

**What it takes to reach BUY (62.0):**
- With ML=50, News=50, Econ=50 as anchors:
  - `0.35*T + 0.25*S ≥ 62 - 20 = 42`
  - If S=50: T ≥ (42 - 12.5) / 0.35 = **84.3** — requires RSI oversold + MACD + EMA200 + BB all bullish
  - If T=S=70: `0.35*70 + 0.25*70 = 42` → exactly 62.0 — barely BUY

---

## Exact Rejection Rules per Message

### Message 1: "Market direction is unclear"

**Trigger:** `signal_service.py:303-306`
```python
if signal_type == "NEUTRAL" or entry is None or stop_loss is None:
    result["plain_explanation"] = (
        "⚪ NEUTRAL — Bozor noaniq. Savdo qilmang.\n"
        "⚪ NEUTRAL — Market unclear. Do not trade."
    )
```

**Activated when:**
- `combined_score` is between `38.0` and `62.0` (neutral zone), OR
- `signal_type` was set to `"NO TRADE"` by confluence conflict and `entry` or `stop_loss` is None

**Exact rejection rule:** `38.0 < combined_score < 62.0` → `signal_type = "NEUTRAL"` → `plain_explanation` = "Market unclear"

---

### Message 2: "Multi-timeframe conflict detected"

**Trigger:** `routers/signals.py:101-110` (sets `signal_type = "NO TRADE"`) + frontend display of `confluence.alignment == "conflict"`

```python
else:  # conflict
    composite = max(0.0, composite - 10)
    if composite < 70 and result.get("signal_type") != "NO TRADE":
        result["signal_type"] = "NO TRADE"
        result["direction"]   = "neutral"
        result["stop_loss"]   = None
        result["take_profit"] = None
        result["tp1"]         = None
        result["risk_reward"] = None
```

**Activated when:**
1. H4 EMA20 < EMA50 but primary signal is BUY (or vice versa for SELL), AND
2. `composite_score < 70` after the -10 penalty

**Exact rejection rule:** `H4 EMA direction ≠ signal direction` AND `composite_after_penalty < 70.0`

**Practical consequence:** Any signal with `composite` between 60 and 79.9 that encounters H4 conflict becomes NO TRADE:
- composite=65 → 65-10=55 → NEUTRAL, AND <70 → force NO TRADE
- composite=75 → 75-10=65 → NEUTRAL (< 62 buy threshold), AND <70 → force NO TRADE
- composite=80 → 80-10=70 → still BUY (70 ≥ 62), survives conflict

---

## Per-Signal Component Breakdown Template

When a signal is rejected, these are the values to check:

```
Signal Decision Trace
─────────────────────────────────────────
Symbol:          XAUUSD
Timeframe:       H1 (60 min)
Time:            [timestamp]

SCORES
  Technical:     [value] / 100   (weight 35%)
  SMC:           [value] / 100   (weight 25%)
  ML:            [value] / 100   (weight 20%)   ← 50 = no model
  News:          [value] / 100   (weight 10%)
  Economic:      [value] / 100   (weight 10%)
  Combined:      [value] / 100

TREND ALIGNMENT
  M15 EMA20 vs EMA50:  [bullish|bearish|neutral]
  H1  EMA20 vs EMA50:  [bullish|bearish|neutral]
  H4  EMA20 vs EMA50:  [bullish|bearish|neutral]
  Confluence score:    [value]
  Alignment:           [full|partial|conflict]

COMPOSITE AFTER CONFLUENCE
  Pre-confluence:      [combined]
  Adjustment:          [+8 / +3 / -10]
  Post-confluence:     [final]

MARKET REGIME
  Regime:              [TRENDING_UP|TRENDING_DOWN|RANGING|VOLATILE|LOW_VOLATILITY|NEWS_DRIVEN]
  ADX:                 [value]
  Volatility ratio:    [value]

FINAL CONFIDENCE
  confidence = abs(composite - 50) × 3.33
  Value:               [value] %

REJECTION RULE TRIGGERED
  □ combined_score in neutral zone (38–62): [yes/no]
  □ H4 conflict AND composite < 70: [yes/no]
  □ ML model missing (ml_score=50): [yes/no]
  □ Insufficient candles (< 50): [yes/no]
  □ Risk filter blocked (R:R < 1.5): [yes/no]
─────────────────────────────────────────
```

---

## Root Cause Analysis

### Cause 1 — Missing ML model (highest frequency)

**File:** `backend/services/signal_service.py:175-200`

```python
path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
if not os.path.exists(path):
    return 50.0, ["No ML model"]   # ← anchors ML at dead center
```

When no model exists: ML score = 50.0. This anchors 20% of the composite at the exact center, meaning tech + smc alone must carry the signal past the threshold using only 60% of the weight.

**Fix:** Train the model via `POST /api/v1/ml/train` or `/retrain` Telegram command.

---

### Cause 2 — Confluence conflict threshold too aggressive

**File:** `backend/routers/signals.py:103`

```python
if composite < 70 and result.get("signal_type") != "NO TRADE":
    result["signal_type"] = "NO TRADE"
```

The threshold of `70` is **8 points above** the BUY threshold of `62`. This means:
- Signals with composite 62–69.9 (valid BUY) are killed by H4 conflict
- The band where H4 conflict kills signals is 62.0 to 79.9 — **a 18-point kill zone**

Any time H4 EMA is in an opposing short-term correction (common in ranging/volatile markets), the system rejects all signals below 80 composite.

**Fix options:**
- Lower the conflict kill threshold from `70` to `65` (reduces kill zone to 62–74.9)
- Or require *both* H4 and H1 to conflict before rejecting (single-TF veto is too harsh)

---

### Cause 3 — RSI neutral deadzone

**File:** `backend/services/signal_service.py:131-138`

RSI between 45 and 55 contributes **zero** to both bull and bear signal counts. In ranging markets where RSI oscillates around 50, this eliminates one of the most important indicators.

```python
if rsi < 30:    bull += 30
elif rsi < 45:  bull += 15
elif rsi > 70:  bear += 30
elif rsi > 55:  bear += 15
# else (45–55): nothing — zero contribution
```

**Fix:** Add a weak signal for 45–55 range based on direction (e.g., `rsi > 50 → bull += 8`, `rsi < 50 → bear += 8`).

---

### Cause 4 — Economic score direction always neutral

**File:** `backend/services/calendar_service.py:173`

```python
return {
    "direction": "neutral",  # ← hardcoded, never changes
    "score": score,
    ...
}
```

The economic score can be > 50 (when USD high-impact events are present), but its direction is never set to bullish or bearish. The numeric score affects the composite, but for the `reasoning_structured` display, the econ layer always shows "neutral". The 10% weight is only half-utilized.

**Fix:** Decode direction from the event type or the actual vs. forecast values.

---

### Cause 5 — News direction threshold too strict

**File:** `backend/services/news_service.py:194-197`

```python
"direction": (
    "bullish" if bullish / total > 0.55 else
    "bearish" if bearish / total > 0.55 else
    "neutral"
),
```

Requires a super-majority (55%) of articles to have the same sentiment. In normal mixed-news environments: e.g., 8 neutral + 4 bullish + 3 bearish out of 15 articles = 27% bullish → stays neutral even though bullish articles outnumber bearish.

The `score` field does shift correctly (50 + (bull-bear)/total × 40), but `direction` stays neutral.

**Fix:** Lower threshold from 55% to 45%, or use score-based direction (`score > 55 → bullish`).

---

## Recommended Immediate Fixes

Listed in order of impact:

### Fix 1: Train ML model (immediate impact, no code change)
```bash
curl -X POST http://localhost:8001/api/v1/ml/train \
  -H "Authorization: Bearer <token>" \
  -d '{"symbol": "XAUUSD", "timeframe": "60"}'
```

### Fix 2: Lower confluence conflict kill threshold

**File:** `backend/routers/signals.py:103`

```python
# BEFORE
if composite < 70 and result.get("signal_type") != "NO TRADE":

# AFTER — only kill signals where composite doesn't clear threshold even without conflict
if composite < 65 and result.get("signal_type") != "NO TRADE":
```

### Fix 3: Fix RSI neutral deadzone

**File:** `backend/services/signal_service.py` — in `_technical_score()`

```python
# Add after the rsi > 55 branch:
elif 50 < rsi <= 55:
    bull += 5; parts.append(f"RSI {rsi:.1f} mild bullish")
elif 45 <= rsi < 50:
    bear += 5; parts.append(f"RSI {rsi:.1f} mild bearish")
```

### Fix 4: Fix economic score direction

**File:** `backend/services/calendar_service.py:157-173`

```python
# Replace "direction": "neutral" with:
usd_score = 50.0 + high_usd * 5
direction = "bullish" if usd_score > 60 else ("bearish" if usd_score < 40 else "neutral")
```

### Fix 5: Lower news direction threshold

**File:** `backend/services/news_service.py:194`

```python
# BEFORE: > 0.55
# AFTER:
"direction": (
    "bullish" if score > 55 else
    "bearish" if score < 45 else
    "neutral"
),
```

---

## Effect of Fixes on Score Simulation

Re-running the typical neutral scenario from above **after all fixes**:

| Component | Before fix | After fix |
|-----------|-----------|-----------|
| Technical | 66.7 | 68.5 (RSI 52 now adds weak bull) |
| SMC | 50.0 | 50.0 (unchanged) |
| ML | 50.0 → model trained | 63.5 (typical after training) |
| News | 50.0 | 52.0 (lower threshold shows mild bull) |
| Economic | 50.0 | 50.0 (neutral if no events) |
| **Combined** | **55.8 → NEUTRAL** | **59.5 → still NEUTRAL** |

Even with all fixes, the scenario above (RSI=52, mild MACD, no strong structure) stays in neutral because XAUUSD genuinely lacks conviction at that moment. That is correct behavior. The fixes primarily reduce false NO TRADE calls in situations where the score was 62–69 and H4 was in a short-term correction.

---

## Files Involved

| File | Role | Key Lines |
|------|------|-----------|
| `backend/routers/signals.py` | Entry point, confluence application, NO TRADE override | 77-113, 175-179 |
| `backend/services/signal_service.py` | Core scoring, NEUTRAL/BUY/SELL decision, plain_explanation | 125-166, 235-241, 303-306 |
| `src/signals/scorer.py` | `confluence_score()` (EMA-based per-TF alignment) | 192-244 |
| `backend/services/news_service.py` | News sentiment score and direction | 179-202 |
| `backend/services/calendar_service.py` | Economic score (direction always neutral) | 157-173 |
| `backend/config.py` | Threshold config: BUY=62, SELL=38, MIN_CONF=65 | 28-30 |
| `backend/core/constants.py` | Signal weights: T=35%, S=25%, ML=20%, N=10%, E=10% | all |
| `.env` | Runtime threshold overrides | SIGNAL_BUY_THRESHOLD etc. |
