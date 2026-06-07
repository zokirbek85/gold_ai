import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base, SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)


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
    log.info("Database tables created/verified")


def _create_admin_user() -> None:
    from models.user import User
    from routers.auth import hash_password
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == "admin@gold.ai").first()
        if not existing:
            admin = User(
                email="admin@gold.ai",
                password_hash=hash_password("admin123"),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            log.info("Admin user created: admin@gold.ai / admin123")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/v1/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "gold-ai", "version": "3.0.0"}
