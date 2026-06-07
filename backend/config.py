from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://goldai:goldai123@db:5432/goldai"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "your-secret-key-change-in-production-min-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ML_MODEL_DIR: str = "/app/models"
    CORS_ORIGINS: str = "http://localhost:3000,http://frontend:3000,http://localhost:4000"
    TWELVEDATA_API_KEY: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_db_url(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
