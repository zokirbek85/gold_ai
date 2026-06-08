from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.ai.routes import router as ai_router
from src.api.admin.routes import router as admin_router
from src.api.auth.routes import router as auth_router
from src.api.backtesting.routes import router as backtesting_router
from src.api.economic_calendar.routes import router as econ_router
from src.api.indicators.routes import router as indicators_router
from src.api.market_data.routes import router as market_data_router
from src.api.ml.routes import router as ml_router
from src.api.ml_feedback import router as ml_feedback_router
from src.api.news.routes import router as news_router
from src.api.patterns.routes import router as patterns_router
from src.api.realtime.routes import router as realtime_router
from src.api.journal.routes import router as journal_router
from src.api.signals.routes import router as signals_router
from src.api.smc.routes import router as smc_router
from src.api.telegram.routes import router as telegram_router
from src.config.settings import settings
from src.market_data.scheduler import connect_mt4, disconnect_mt4, init_scheduler, shutdown_scheduler

app = FastAPI(
    title="GOLD AI — Trading Intelligence Platform",
    description="Production-grade XAUUSD analysis: Technical + SMC + ML + AI + News",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

_CORS_ORIGINS = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])

# Market Data
app.include_router(market_data_router, prefix="/api/v1/market-data", tags=["Market Data"])
app.include_router(realtime_router, prefix="/api/v1/realtime", tags=["Realtime WebSocket"])

# Analysis
app.include_router(indicators_router, prefix="/api/v1/indicators", tags=["Technical Indicators"])
app.include_router(patterns_router, prefix="/api/v1/patterns", tags=["Pattern Detection"])
app.include_router(smc_router, prefix="/api/v1/smc", tags=["Smart Money Concepts"])

# Intelligence
app.include_router(news_router, prefix="/api/v1/news", tags=["News Intelligence"])
app.include_router(econ_router, prefix="/api/v1/economic-calendar", tags=["Economic Calendar"])
app.include_router(ml_router, prefix="/api/v1/ml", tags=["Machine Learning"])
app.include_router(ml_feedback_router, prefix="/api/v1", tags=["ML Feedback"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["AI Analysis"])

# Signals + Trading
app.include_router(signals_router,  prefix="/api/v1/signals",  tags=["Trading Signals"])
app.include_router(journal_router,  prefix="/api/v1/journal",  tags=["Trade Journal"])
app.include_router(backtesting_router, prefix="/api/v1/backtesting", tags=["Backtesting"])

# Notifications
app.include_router(telegram_router, prefix="/api/v1/telegram", tags=["Telegram"])

# Admin
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])


@app.on_event("startup")
def on_startup():
    connect_mt4()
    init_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    shutdown_scheduler()
    disconnect_mt4()


@app.get("/api/v1/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": "gold-ai",
        "version": "2.0.0",
        "env": settings.ENV,
    }
