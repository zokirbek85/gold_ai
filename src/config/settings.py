import os
from typing import Optional
from pydantic import BaseModel


class Settings(BaseModel):
    ENV: str = "development"
    PROJECT_NAME: str = "gold-ai"
    DATABASE_URL: Optional[str] = None
    SECRET_KEY: str = "changemeplease_set_env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # MT4 ZeroMQ bridge settings
    MT4_HOST: str = "localhost"
    MT4_CMD_PORT: int = 32768
    MT4_DATA_PORT: int = 32769
    MT4_SYMBOLS: Optional[str] = None
    MT4_TIMEFRAMES: Optional[str] = None
    MT4_INGEST_INTERVAL_SECONDS: Optional[int] = None
    INDICATOR_CALC_INTERVAL_SECONDS: Optional[int] = None
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # ML
    ML_MODEL_DIR: str = "models"

    # News
    NEWS_INGEST_INTERVAL_SECONDS: int = 1800

    # CORS — comma-separated list of allowed origins, or empty for "*"
    CORS_ORIGINS: Optional[str] = None


def _load_settings() -> Settings:
    env = os.environ
    data = {
        "ENV": env.get("ENV", "development"),
        "PROJECT_NAME": env.get("PROJECT_NAME", "gold-ai"),
        "DATABASE_URL": env.get("DATABASE_URL"),
        "SECRET_KEY": env.get("SECRET_KEY", "changemeplease_set_env"),
        "ACCESS_TOKEN_EXPIRE_MINUTES": int(env.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15")),
        "REFRESH_TOKEN_EXPIRE_DAYS": int(env.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        "MT4_HOST": env.get("MT4_HOST", "localhost"),
        "MT4_CMD_PORT": int(env.get("MT4_CMD_PORT", "32768")),
        "MT4_DATA_PORT": int(env.get("MT4_DATA_PORT", "32769")),
        "MT4_SYMBOLS": env.get("MT4_SYMBOLS"),
        "MT4_TIMEFRAMES": env.get("MT4_TIMEFRAMES"),
        "MT4_INGEST_INTERVAL_SECONDS": int(env.get("MT4_INGEST_INTERVAL_SECONDS")) if env.get("MT4_INGEST_INTERVAL_SECONDS") else None,
        "INDICATOR_CALC_INTERVAL_SECONDS": int(env.get("INDICATOR_CALC_INTERVAL_SECONDS")) if env.get("INDICATOR_CALC_INTERVAL_SECONDS") else None,
        "REDIS_URL": env.get("REDIS_URL", "redis://localhost:6379/0"),
        "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY"),
        "OPENAI_API_KEY": env.get("OPENAI_API_KEY"),
        "TELEGRAM_BOT_TOKEN": env.get("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": env.get("TELEGRAM_CHAT_ID"),
        "ML_MODEL_DIR": env.get("ML_MODEL_DIR", "models"),
        "NEWS_INGEST_INTERVAL_SECONDS": int(env.get("NEWS_INGEST_INTERVAL_SECONDS", "1800")),
        "CORS_ORIGINS": env.get("CORS_ORIGINS"),
    }
    return Settings(**data)


settings = _load_settings()
