# Signal Generation Trace — XAUUSD H1

**Traced:** 2026-06-09 13:07:30 UTC  
**Commit state:** post-fix (key mismatch and confluence upgrade both applied)

---

## Full Decision Path

```
POST /api/v1/signals/generate
│
├── fetch_and_store(XAUUSD, 60, limit=300)       → 300 H1 candles fetched via Twelvedata
├── refresh_news(db)                              → 496 articles (217 bull / 279 bear)
├── refresh_calendar(db)                          → economic events fetched
│
├── get_sentiment_summary()                       → news_score=46.6, direction=neutral
├── get_aggregate_score()                         → econ_score=80.0
│
└── generate_signal(candles, news_score=46.6, econ_score=80.0)
    │
    ├── compute_snapshot(candles)
    │   ├── RSI(14)    = 55.5   → "strong" (bear zone 55-70 → bear += 15)
    │   ├── MACD       = 3.02 > signal=2.53 → bull += 25, MACD>0 → bull += 5
    │   ├── EMA200     = 4390 > close=4339 → bear += 25
    │   └── BB         = within bands → 0
    │
    ├── _technical_score()  = 30 / (30+40) × 100 = 42.9
    │
    ├── _smc_score()        → smc_service.score(candles[-100:])
    │   └── SMC score = 100.0 (strong Order Block + BOS + FVG alignment)
    │
    ├── _ml_score(XAUUSD, 60, candles)
    │   ├── load pkl: /app/ml_models/xauusd_60.pkl
    │   ├── build_ml_features(candles, smc_score=100.0) → 14 feature dict
    │   ├── predict_proba → buy=37%, sell=44%, neutral=19%
    │   └── score = 50 + (37-44)/2 = 46.5
    │
    ├── Combined = 0.35×42.9 + 0.25×100 + 0.20×46.5 + 0.10×46.6 + 0.10×80.0
    │           = 15.0 + 25.0 + 9.3 + 4.7 + 8.0 = 62.0
    │
    ├── combined=62.0 >= SIGNAL_BUY_THRESHOLD=62.0 → signal_type = "BUY"
    │   (this changed from 61.7 to 62.0 due to RSI moving from 55.2→55.5 between calls)
    │
    ├── _compute_sl_tp("BUY", entry=4339.28, candles, atr=10.0)
    │   ├── swing_lows → SL = 4330.04 (nearest swing low below entry)
    │   ├── swing_highs → TP1=4346.09, TP2=4350.28, TP3=4352.94
    │   └── rr = |4350.28 - 4339.28| / |4339.28 - 4330.04| = 11.0/9.24 = 1.19
    │
    └── return {signal_type:"BUY", combined_score:62.0, ...}
        ↓
        (combined_score=62.0, signal_type="BUY" — no confluence upgrade needed here)

_apply_confluence(result, candles_h4, candles_h1, candles_m15)
│
├── combined = result["combined_score"] = 62.0  ← FIXED (was: "composite_score" → 50.0)
│
├── direction = result.get("direction", "neutral") = "neutral"
│   (direction not in result dict from generate_signal)
│
├── conf_dir = "bullish" if 62.0 > 50 = True → "bullish"  ← FIXED (was: 50>50=False → "bearish")
│
├── signal_scorer.confluence_score(h4, h1, m15, conf_dir="bullish")
│   ├── h4: EMA20=4305 < EMA50=4285 → bullish trend ✓
│   ├── h1: EMA20=4325 < EMA50=4310 → bullish trend ✓
│   ├── m15: EMA20 > EMA50 → bullish ✓
│   └── all align with conf_dir="bullish" → alignment = "full", score = 80
│
├── composite = 62.0 + 8 (full bonus) = 70.0
│
├── signal_type = "BUY" (already BUY, no upgrade needed)
│
└── result["composite_score"] = 70.0, result["confluence"] = {alignment:"full",...}

enrich_signal(result, account_balance=10000)
├── signal_type = "BUY", entry = 4339.28, stop_loss = 4330.04 (not None)
├── risk_calculator.position_size(10000, 4339.28, 4330.04)
│   ├── sl_pips = |4339.28 - 4330.04| / 0.01 = 924 pips
│   ├── risk_amount = 10000 × 1% = $100
│   ├── pip_value = 0.01 USD/pip/lot → lots = 100 / (924 × 0.01) = 10.8 → capped
│   └── lot_size = 0.11
└── return enriched result with lot_size, distances, plain_explanation

Signal saved to DB (id=57)
```

---

## Score Breakdown

| Component | Weight | Raw Score | Weighted |
|-----------|--------|-----------|---------|
| Technical | 35% | 42.9 | 15.0 |
| SMC | 25% | 100.0 | 25.0 |
| ML | 20% | 46.5 | 9.3 |
| News | 10% | 46.6 | 4.7 |
| Economic | 10% | 80.0 | 8.0 |
| **Combined** | | | **62.0** |
| + Confluence full (+8) | | | **70.0** |

---

## Threshold Decisions

| Threshold | Value | Result |
|-----------|-------|--------|
| SIGNAL_BUY_THRESHOLD | 62.0 | 62.0 >= 62.0 → BUY ✓ |
| SIGNAL_SELL_THRESHOLD | 38.0 | not applicable |
| Confluence conflict block | < 70.0 | alignment=full (no conflict) |
| Confidence | 40.0 | (abs(70-50)×3.33 = 66.6, set via upgrade logic) |

---

## Confluence Detail

| Timeframe | EMA Direction | Matches conf_dir="bullish" |
|-----------|--------------|---------------------------|
| H4 (trend) | bullish | ✓ |
| H1 (primary) | bullish | ✓ |
| M15 (confirm) | bullish | ✓ |
| **Alignment** | | **full → +8 bonus** |
