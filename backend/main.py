import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import engine, Base, SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

# ── Rate limiter (shared across all routers) ──────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Sentry (graceful no-op when SENTRY_DSN is blank) ─────────────────────────
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
            environment="production",
        )
        log.info("Sentry initialised")
    except Exception as exc:
        log.warning("Sentry init failed: %s", exc)


def _create_tables() -> None:
    import models.user
    import models.candle
    import models.signal
    import models.news
    import models.economic_calendar
    import models.backtest
    import models.ml_model
    import models.system_log
    Base.metadata.create_all(bind=engine)

    try:
        from src.machine_learning.feedback_models import Base as FeedbackBase
        FeedbackBase.metadata.create_all(bind=engine)
        log.info("ML feedback tables created/verified")
    except Exception as exc:
        log.warning("ML feedback tables skipped: %s", exc)

    log.info("Database tables created/verified")


def _create_admin_user() -> None:
    from models.user import User
    from routers.auth import hash_password
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if not existing:
            admin = User(
                email=email,
                password_hash=hash_password(password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            log.info("Admin user created: %s (password from ADMIN_PASSWORD env)", email)
    except Exception:
        log.exception("Failed to create admin user")
        db.rollback()
    finally:
        db.close()


def _initial_ingest() -> None:
    """Run in a background thread to avoid blocking startup."""
    from database import SessionLocal
    from services.market_service import ingest_historical
    from services.news_service import get_or_generate_news
    from services.calendar_service import get_or_generate_events

    db = SessionLocal()
    try:
        log.info("Starting initial data ingestion…")
        ingest_historical(db, "XAUUSD")
        get_or_generate_news(db)
        get_or_generate_events(db)
        log.info("Initial data ingestion complete")
    except Exception:
        log.exception("Initial data ingestion failed")
    finally:
        db.close()

    # After ingestion, auto-train ML models for any timeframe that has no saved model
    _auto_train_missing_models()


def _auto_train_missing_models() -> None:
    """Train ML models for timeframes that have no .pkl file yet, using all DB candles."""
    import os
    from database import SessionLocal
    from models.candle import Candle
    from services import ml_service
    from config import settings

    # GOLD_AI uses these 7 timeframes; prioritise H1 and H4 first
    TIMEFRAMES = ["60", "240", "15", "1440", "5", "30", "1"]

    db = SessionLocal()
    try:
        for tf in TIMEFRAMES:
            model_path = os.path.join(settings.ML_MODEL_DIR, f"xauusd_{tf}.pkl")
            if os.path.exists(model_path):
                log.info("ML model already exists for XAUUSD/%s — skipping auto-train", tf)
                continue

            rows = (
                db.query(Candle)
                .filter(Candle.symbol == "XAUUSD", Candle.timeframe == tf)
                .order_by(Candle.timestamp.asc())
                .all()
            )
            candles = [
                {"open": r.open, "high": r.high, "low": r.low,
                 "close": r.close, "volume": r.volume}
                for r in rows
            ]

            if len(candles) < 200:
                log.info("Not enough candles for XAUUSD/%s (%d) — skipping auto-train", tf, len(candles))
                continue

            log.info("Auto-training ML for XAUUSD/%s using %d candles…", tf, len(candles))
            try:
                result = ml_service.train("XAUUSD", tf, candles)
                log.info(
                    "Auto-train XAUUSD/%s done: status=%s samples=%s accuracy=%s",
                    tf, result.get("status"), result.get("samples"), result.get("accuracy"),
                )
            except Exception:
                log.exception("Auto-train failed for XAUUSD/%s", tf)
    except Exception:
        log.exception("_auto_train_missing_models failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _create_tables()
    _create_admin_user()

    # Start scheduler
    from services.scheduler import init_scheduler
    init_scheduler()

    # Kick off background ingest (non-blocking)
    t = threading.Thread(target=_initial_ingest, daemon=True)
    t.start()

    # Start Twelvedata real-time WebSocket feed
    from services import twelvedata_service
    twelvedata_service.start(settings.TWELVEDATA_API_KEY)

    # Start Telegram bot polling
    from services.telegram_service import start_polling
    start_polling()

    log.info("Gold AI backend started on port 8001")
    yield

    # Shutdown
    from services.scheduler import shutdown_scheduler
    shutdown_scheduler()
    log.info("Gold AI backend stopped")


app = FastAPI(
    title="Gold AI — Trading Intelligence Platform",
    description="XAUUSD analysis: Technical + SMC + ML + AI + News",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Rate limiter state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    log.info("Prometheus /metrics endpoint registered")
except ImportError:
    log.debug("prometheus-fastapi-instrumentator not installed — metrics disabled")

from routers.auth import router as auth_router
from routers.market_data import router as market_data_router
from routers.indicators import router as indicators_router
from routers.patterns import router as patterns_router
from routers.smc import router as smc_router
from routers.signals import router as signals_router
from routers.news import router as news_router
from routers.economic_calendar import router as econ_router
from routers.ml import router as ml_router
from routers.ai import router as ai_router
from routers.backtesting import router as backtesting_router
from routers.admin import router as admin_router
from routers.forecast import router as forecast_router
from routers.telegram_service import router as telegram_router
from routers.risk import router as risk_router
from src.api.ml_feedback import router as ml_feedback_router

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(market_data_router, prefix="/api/v1/market-data", tags=["Market Data"])
app.include_router(indicators_router, prefix="/api/v1/indicators", tags=["Indicators"])
app.include_router(patterns_router, prefix="/api/v1/patterns", tags=["Patterns"])
app.include_router(smc_router, prefix="/api/v1/smc", tags=["SMC"])
app.include_router(signals_router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(news_router, prefix="/api/v1/news", tags=["News"])
app.include_router(econ_router, prefix="/api/v1/economic-calendar", tags=["Economic Calendar"])
app.include_router(ml_router, prefix="/api/v1/ml", tags=["ML"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["AI"])
app.include_router(backtesting_router, prefix="/api/v1/backtesting", tags=["Backtesting"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(forecast_router, prefix="/api/v1/forecast", tags=["Forecast"])
app.include_router(telegram_router, prefix="/api/v1/telegram", tags=["Telegram"])
app.include_router(ml_feedback_router, prefix="/api/v1", tags=["ML Feedback"])
app.include_router(risk_router, prefix="/api/v1/risk", tags=["Risk Management"])


@app.get("/api/v1/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "gold-ai", "version": "3.0.0"}
