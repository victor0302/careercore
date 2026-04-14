"""Application configuration via pydantic-settings.

All values are read from environment variables (or .env file).
Access the singleton with: from app.core.config import get_settings; settings = get_settings()
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_ENV: Literal["development", "production"] = "development"
    APP_VERSION: str = "0.1.0"

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "careercore-uploads"
    FILE_DOWNLOAD_URL_TTL_SECONDS: int = 300

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # AI
    AI_PROVIDER: Literal["anthropic", "mock"] = "mock"
    ANTHROPIC_API_KEY: str = ""
    AI_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    AI_SONNET_MODEL: str = "claude-sonnet-4-6"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Token budgets
    FREE_TIER_DAILY_TOKEN_BUDGET: int = 50_000
    STANDARD_DAILY_TOKEN_BUDGET: int = 200_000

    # CORS — comma-separated list of origins
    CORS_ORIGINS: str = "http://localhost:3000"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
