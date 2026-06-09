# Gold AI — Full Refactor Plan

**Date:** 2026-06-09  
**Auditor:** Principal Quant Engineer / Senior AI Architect  
**Codebase:** FastAPI 0.111 + Next.js 15 + PostgreSQL + Redis  

---

## Subsystem Scores (1–10)

| # | Subsystem | Score | Priority | Business Impact |
|---|-----------|-------|----------|-----------------|
| 1 | Security | **2/10** | CRITICAL | Exposed API keys, hardcoded tokens, no rate-limiting |
| 2 | Architecture | **4/10** | HIGH | Dual code trees, sys.path hacks, no DI |
| 3 | Telegram Service | **3/10** | HIGH | localhost calls fail in Docker, ephemeral chat state |
| 4 | ML Integration | **4/10** | HIGH | Two separate ML pipelines not connected |
| 5 | Database | **5/10** | HIGH | Missing indexes, deprecated timestamps, no updated_at |
| 6 | DevOps / CI | **4/10** | HIGH | Nginx unused, no GitHub Actions, no health checks |
| 7 | Signal Engine | **6/10** | MEDIUM | Hardcoded thresholds, magic numbers |
| 8 | Risk Management | **6/10** | MEDIUM | No daily-loss / max-trades tracking |
| 9 | Market Data | **6/10** | MEDIUM | Only Twelvedata+yfinance, no failover chain |
| 10 | SMC Engine | **7/10** | MEDIUM | Good quality, minor tuning needed |
| 11 | Frontend | **7/10** | MEDIUM | Good structure, missing error boundaries |
| 12 | ML Models | **5/10** | MEDIUM | XGBoost/LGBMCatBoost isolated from backend ML path |
| 13 | Observability | **2/10** | MEDIUM | No Prometheus, Grafana, or Sentry |
| 14 | Testing | **5/10** | MEDIUM | Tests exist but coverage < 40% |
| 15 | Documentation | **3/10** | LOW | Minimal docs beyond README |

---

## Execution Order (by Business Impact)

```
Phase  1 — AUDIT_REPORT.md         (done — this file accompanies it)
Phase  4 — Security Hardening       ← EXECUTE FIRST (exposed secrets)
Phase  2 — Architecture Fix         ← Unblock all downstream changes
Phase  3 — Database Optimisation    ← Foundation for reliable queries
Phase 14 — DevOps (Docker+CI)       ← Required before any deploy
Phase  5 — Signal Engine Refactor   ← Core product quality
Phase  6 — Risk Management          ← Protect capital
Phase  7 — ML Upgrade               ← Ensemble + walk-forward
Phase  8 — Market Regime Detector   ← Adaptive signals
Phase  9 — Data Pipeline            ← Reliability
Phase 10 — MT5 Execution Engine     ← Live trading gate
Phase 11 — Telegram Upgrade         ← User-facing fix
Phase 12 — Frontend Upgrade         ← UX polish
Phase 13 — Observability            ← Production readiness
Phase 15 — Testing                  ← Quality gate
Phase 16 — Documentation            ← Maintenance
```

---

## Critical Findings Summary

### SECURITY (Score: 2/10)
- `docker-compose.yml` contains **plaintext** `TWELVEDATA_API_KEY` and `TELEGRAM_BOT_TOKEN`
- `backend/main.py` hardcodes admin credentials: `admin@gold.ai / admin123`
- `backend/config.py` default `SECRET_KEY` is `"your-secret-key-change-in-production-min-32-chars"`
- No rate limiting on FastAPI endpoints (Nginx rate-limit config exists but Nginx not in compose)
- JWT refresh tokens have no blacklist — stolen refresh tokens valid forever
- `.env` file committed to repo with `SECRET_KEY=change_me_to_secure_value`

### ARCHITECTURE (Score: 4/10)
- **Two separate code trees**: `backend/` (active FastAPI app) and `src/` (ML, SMC, risk)
- `backend/services/signal_service.py` uses `sys.path.insert(0, ...)` hack to import `src/`
- `backend/main.py` imports `from src.api.ml_feedback import router`
- `backend/routers/signals.py` imports `from src.signals.scorer import signal_scorer`
- No dependency injection — all services are module-level singletons
- No repository pattern — services mix business logic with raw SQLAlchemy queries

### TELEGRAM SERVICE (Score: 3/10)
- All internal API calls use `http://localhost:8001` which **fails inside Docker containers**
- Registered chat IDs stored in an in-memory Python `set` — lost on every restart
- `TOKEN` read at module import time using `os.environ.get()` — fails if env not set at import

### ML INTEGRATION (Score: 4/10)
- `backend/services/ml_service.py` uses only `RandomForestClassifier`
- `src/machine_learning/trainer.py` has XGBoost/LightGBM/CatBoost ensemble but is **never called** from the backend signal pipeline
- `FEATURE_NAMES` list defined in **3 separate places** — can diverge silently
- No walk-forward validation, no time-series CV
- Model retraining in scheduler only trains for `XAUUSD` H1

### DATABASE (Score: 5/10)
- `Candle` table has individual indexes on `symbol`, `timeframe`, `timestamp` but **no composite index** on `(symbol, timeframe, timestamp)` — all signal queries filter all three
- All models use `datetime.utcnow` (deprecated in Python 3.12+, removed in 3.14)
- Business models (`Signal`, `News`, `EconomicEvent`) missing `updated_at`
- `upsert_candles()` uses PostgreSQL-specific `pg_insert` — breaks SQLite test env
- `dev.db` (SQLite dev file) committed to repo

### DEVOPS (Score: 4/10)
- `nginx/nginx.conf` exists but Nginx **not included in `docker-compose.yml`**
- `nginx.conf` points to `backend:8000` but backend runs on port `8001`
- No `depends_on` health check for the backend service in docker-compose
- No GitHub Actions CI/CD pipeline
- No Prometheus metrics endpoint
- No Sentry DSN configured

---

## Phase Execution Details

### Phase 4 — Security Hardening
**Files to change:**
- `docker-compose.yml` — remove all hardcoded secrets, use `${VAR}` from .env
- `.env.example` — document all required variables
- `backend/config.py` — add `SIGNAL_CONFIDENCE_THRESHOLD`, `TELEGRAM_CHAT_IDS`
- `backend/main.py` — remove hardcoded admin password, read from env
- `backend/routers/auth.py` — add token blacklist (Redis), add `logout` endpoint
- Add `slowapi` rate limiting to FastAPI app

### Phase 2 — Architecture Fix
**Goal:** Eliminate dual code trees, remove all sys.path hacks.
**Strategy:** Merge `src/` modules into `backend/` using proper Python packages.
- Move `src/risk_management/` → `backend/core/risk/`
- Move `src/signals/scorer.py` → `backend/services/signal_scorer.py`
- Move `src/machine_learning/` → `backend/ml/`
- Move `src/smc/` → `backend/core/smc/`
- Delete `sys.path.insert()` calls
- Update all imports

### Phase 3 — Database Optimisation
**Files to change:**
- `backend/models/*.py` — add `updated_at`, fix `datetime.utcnow`
- `alembic/versions/0005_indexes_and_timestamps.py` — new migration
- `backend/services/market_service.py` — replace `pg_insert` with cross-DB upsert

### Phase 5 — Signal Engine Refactor
- Extract thresholds to `settings.py` (`BUY_THRESHOLD=62`, `SELL_THRESHOLD=38`)
- Extract `FEATURE_NAMES` to a single shared constant file
- Add `MarketRegimeDetector` integration (Phase 8 prerequisite)

### Phase 6 — Advanced Risk Management
- Add `DailyRiskTracker` class with Redis backend
- Track open trades, daily loss, weekly loss
- Expose `/api/v1/risk/status` endpoint

### Phase 7 — ML Upgrade
- Unify `backend/services/ml_service.py` and `src/machine_learning/trainer.py`
- Create `backend/ml/ensemble.py` that wraps RandomForest + XGBoost + LightGBM + CatBoost
- Add walk-forward validation in `backend/ml/validation.py`
- Store `FEATURE_NAMES` in `backend/ml/features.py` (single source of truth)

### Phase 8 — Market Regime Detection
- Create `backend/core/regime.py` — `MarketRegimeDetector` class
- Regimes: Trending / Ranging / Volatile / Low-Vol / News-Driven
- Signal service queries regime before generating signal
- Adjust SMC weight: Ranging → increase SMC; Trending → increase Technical

### Phase 9 — Data Pipeline
- Create `backend/data/providers/` with `TwelvedataProvider`, `YfinanceProvider`, `PolygonProvider`
- `ProviderChain` class with automatic fallback
- Config: `DATA_PROVIDERS=twelvedata,polygon,yfinance`

### Phase 10 — MT5 Execution Engine
- Create `backend/execution/mt5.py` — `MT5ExecutionService`
- Paper trading mode (logs only)
- Live trading mode (MT5 connection)
- Expose `/api/v1/execution/` endpoints

### Phase 11 — Telegram Upgrade
- Fix all `http://localhost:8001` → `http://backend:8001` (Docker-internal)
- Persist chat IDs in Redis key `tg:registered_chats`
- Add `/forecast`, `/account`, `/performance` commands
- Extract handlers to separate files

### Phase 12 — Frontend Upgrade
- Add error boundaries to all pages
- Add React Query error states
- Improve mobile responsiveness

### Phase 13 — Observability
- Add `prometheus-fastapi-instrumentator` to backend
- Add `/metrics` endpoint
- Add `docker-compose.monitoring.yml` with Prometheus + Grafana
- Add Sentry SDK init in `backend/main.py`

### Phase 14 — DevOps
- Add `nginx` service to `docker-compose.yml`
- Fix nginx port: `8000` → `8001`
- Add `backend` health check in compose
- Create `.github/workflows/ci.yml` with test + lint + build

### Phase 15 — Testing
- Fix `conftest.py` to use SQLite for all tests
- Add `tests/test_risk_management.py`
- Add `tests/test_ml_ensemble.py`
- Add `tests/test_regime_detector.py`
- Add `tests/test_signal_engine.py`
- Target: 80% coverage on `backend/services/`

### Phase 16 — Documentation
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/DEPLOYMENT.md`
- `docs/ML.md`
- `docs/TRADING_ENGINE.md`
- `docs/RISK_MANAGEMENT.md`
- `docs/SECURITY_REPORT.md`
- `docs/DATABASE_REVIEW.md`

---

## Non-Negotiable Rules During Refactor

1. **Never break existing functionality** — all refactors must pass existing tests
2. **No synthetic/fake market data** — real data only (Twelvedata → yfinance)
3. **Small, focused commits** — one concern per commit
4. **Every secret goes to .env** — never hardcode credentials
5. **All DB changes via Alembic** — never `Base.metadata.create_all()` in production
