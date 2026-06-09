from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg2://goldai:goldai123@db:5432/goldai"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-me-to-a-64-char-random-secret-in-production-env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ML_MODEL_DIR: str = "/app/models"
    CORS_ORIGINS: str = "http://localhost:3000,http://frontend:3000"

    # ── External APIs (no hardcoded defaults) ─────────────────────────────────
    TWELVEDATA_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SENTRY_DSN: str = ""

    # ── Admin seeding (injected via env, never hardcoded in code) ─────────────
    ADMIN_EMAIL: str = "admin@gold.ai"
    ADMIN_PASSWORD: str = "changeme"

    # ── Internal service URL (Docker-internal name) ───────────────────────────
    INTERNAL_BASE_URL: str = "http://localhost:8001"

    # ── Signal engine thresholds ──────────────────────────────────────────────
    SIGNAL_BUY_THRESHOLD: float = 62.0
    SIGNAL_SELL_THRESHOLD: float = 38.0
    SIGNAL_MIN_CONFIDENCE: float = 65.0

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_db_url(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
