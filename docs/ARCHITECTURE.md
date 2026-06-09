# Gold AI — System Architecture

## Overview

Gold AI is a full-stack trading intelligence platform for XAUUSD (Gold/USD). It combines technical analysis, Smart Money Concepts (SMC), machine learning ensembles, and real-time news sentiment to generate high-confidence trading signals.

```
┌─────────────────────────────────────────────────────┐
│                    Nginx (1.27)                      │
│         /api → backend:8001  /  → frontend:3000      │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐      ┌─────────▼──────────┐
│  FastAPI 0.111  │      │   Next.js 15 (App) │
│  Python 3.11    │      │   TypeScript       │
│  Port 8001      │      │   Port 3000        │
└───────┬────────┘      └────────────────────┘
        │
   ┌────┴──────────────────────┐
   │                            │
┌──▼──────────┐      ┌─────────▼──────────┐
│ PostgreSQL 16│      │    Redis 7          │
│ Primary DB   │      │  Cache + Sessions   │
│ Port 5432    │      │  Port 6379          │
└─────────────┘      └────────────────────┘
```

## Directory Structure

```
gold_ai/
├── backend/                # FastAPI application (Python 3.11)
│   ├── config.py           # Pydantic Settings — all env vars
│   ├── database.py         # SQLAlchemy engine + SessionLocal + Base
│   ├── main.py             # App factory, lifespan, router registration
│   ├── models/             # SQLAlchemy ORM models
│   ├── routers/            # FastAPI route handlers (thin controllers)
│   ├── services/           # Business logic (signal, market, ML, Telegram…)
│   ├── core/               # Shared constants, risk tracker, regime detector
│   │   ├── constants.py    # ML_FEATURE_NAMES, signal weights
│   │   ├── regime.py       # MarketRegimeDetector (6 regimes)
│   │   └── risk_tracker.py # DailyRiskTracker (Redis TTL counters)
│   ├── ml/                 # ML ensemble training + prediction
│   │   └── ensemble.py     # EnsembleTrainer (RF + XGB + LGBM + CatBoost)
│   ├── data/               # Data provider chain
│   │   └── providers.py    # Twelvedata → Polygon → yfinance fallback
│   └── requirements.txt
│
├── src/                    # Legacy code (kept for compatibility)
│   ├── risk_management/    # RiskCalculator (position sizing, RR)
│   ├── machine_learning/   # ML feedback loop
│   ├── signals/            # Signal generation
│   ├── indicators/         # Technical indicators
│   ├── smc/                # SMC analysis
│   └── …
│
├── frontend/               # Next.js 15 App Router
│   ├── app/                # Pages and layouts
│   ├── components/         # Reusable UI components
│   └── lib/                # API client, hooks, utils
│
├── alembic/                # Database migrations
│   └── versions/           # Migration files (0001 → 0005)
│
├── nginx/                  # Nginx reverse proxy config
├── tests/                  # Pytest test suite
├── docker-compose.yml      # Full stack orchestration
└── docs/                   # This directory
```

## Core Subsystems

### 1. Signal Engine

The signal pipeline produces a composite score 0–100 from five weighted components:

| Component   | Weight | Source                         |
|-------------|--------|--------------------------------|
| Technical   | 35%    | RSI, MACD, EMA, Bollinger Bands |
| SMC         | 25%    | Order Blocks, FVG, BOS/CHoCH   |
| ML Ensemble | 20%    | RF + XGB + LGBM + CatBoost     |
| News        | 10%    | Sentiment from news articles   |
| Economic    | 10%    | High-impact calendar events    |

**BUY** when `combined_score ≥ SIGNAL_BUY_THRESHOLD` (default 62)
**SELL** when `combined_score ≤ SIGNAL_SELL_THRESHOLD` (default 38)

Weights are dynamically adjusted by the `MarketRegimeDetector` — e.g., in trending markets, Technical/SMC receive higher weight; in news-driven regimes, News gets more weight.

### 2. ML Ensemble

`backend/ml/ensemble.py` trains and serves an ensemble of four models:

- **RandomForestClassifier** — always trained (sklearn)
- **XGBClassifier** — optional (requires `xgboost`)
- **LGBMClassifier** — optional (requires `lightgbm`)
- **CatBoostClassifier** — optional (requires `catboost`)

Each model is evaluated via **walk-forward time-series cross-validation** (5 folds). Soft-voting weights each model by its walk-forward accuracy, so better models have more influence on the final prediction.

Labels: `-1` (bearish), `0` (neutral), `1` (bullish)

### 3. Market Regime Detection

`backend/core/regime.py` classifies market conditions into 6 regimes:

| Regime        | Trigger                                   |
|---------------|-------------------------------------------|
| TRENDING_UP   | ADX > 25 + positive price slope           |
| TRENDING_DOWN | ADX > 25 + negative price slope           |
| RANGING       | ADX < 25 + range < 1% of midpoint         |
| VOLATILE      | ATR > 1.5× historical average             |
| LOW_VOLATILITY| ATR < 0.6× historical average             |
| NEWS_DRIVEN   | External flag (from economic calendar)    |

### 4. Risk Management

Two layers:

**Trade-level** (`src/risk_management/calculator.py`):
- 1% account risk per trade (configurable)
- Minimum 1:1.5 R:R filter
- Position sizing: `risk_amount / (sl_pips × pip_value)`
- Three take-profit targets at 1.5R, 2R, 3R

**Session-level** (`backend/core/risk_tracker.py`):
- Daily loss limit: 3% of account
- Weekly loss limit: 6% of account
- Max 5 open trades simultaneously
- Max 2 correlated trades (metals, USD majors, JPY group)
- All counters stored in Redis with TTL-based daily/weekly resets

### 5. Data Pipeline

`backend/data/providers.py` implements a provider chain with automatic failover:

```
Twelvedata → Polygon → yfinance
```

Order is controlled by `DATA_PROVIDERS` env var (default: `twelvedata,polygon,yfinance`). Each provider returns a normalized list of candle dicts: `{open, high, low, close, volume, timestamp}`.

### 6. Authentication

JWT-based auth with Redis-backed token blacklist:

- Access token: 30 min TTL, includes `jti` (UUID) claim
- Refresh token: 7 day TTL, includes `jti` claim
- Logout: blacklists access token `jti` in Redis with matching TTL
- Refresh: blacklists old refresh token, issues new token pair (rotation)
- Token blacklist key: `bl:jwt:{jti}`

### 7. Telegram Bot

Long-polling bot with 13 commands: `/start`, `/help`, `/price`, `/signal`, `/news`, `/analysis`, `/forecast`, `/account`, `/ml`, `/accuracy`, `/patterns`, `/retrain`, `/status`.

- Chat IDs persisted to Redis (`tg:registered_chats`) — survive restarts
- Alert filter prevents signal spam (confidence threshold + cooldown)
- All internal API calls use `INTERNAL_BASE_URL` env var (not hardcoded `localhost`)

## Environment Variables

See `.env.example` for the complete list. Required variables:

| Variable       | Description                       |
|----------------|-----------------------------------|
| DATABASE_URL   | PostgreSQL connection string      |
| REDIS_URL      | Redis connection string           |
| SECRET_KEY     | 64-char random hex for JWT        |
| ADMIN_EMAIL    | Initial admin user email          |
| ADMIN_PASSWORD | Initial admin user password       |

## Data Flow: Signal Generation

```
1. Market data fetch (provider chain) → candles[]
2. Technical indicators calculation (RSI, MACD, EMA, ATR, BB)
3. SMC analysis (Order Blocks, FVG, BOS detection)
4. ML ensemble prediction (feature extraction → ensemble vote)
5. News sentiment score (last N articles)
6. Economic calendar score (upcoming high-impact events)
7. Market regime detection (ADX + ATR + price slope)
8. Regime-adjusted weight combination → composite_score
9. Threshold comparison → BUY / SELL / NO TRADE
10. Risk filter (R:R, position size, daily loss limit)
11. Signal persisted to DB + broadcast via Telegram
```
