"""Application configuration via pydantic-settings.

All values are read from environment variables (or .env file).
Access the singleton with: from app.core.config import get_settings; settings = get_settings()
"""

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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
    AI_PROVIDER: Literal["anthropic", "mock", "openai_compatible", "ollama"] = "mock"
    ANTHROPIC_API_KEY: str = ""
    # Model names — override to pin a version or test a different model tier
    AI_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    AI_SONNET_MODEL: str = "claude-sonnet-4-6"
    ai_model_pricing: dict[str, float] = Field(
        default_factory=lambda: {
            "claude-haiku-4-5-20251001": 0.25,
            "claude-sonnet-4-6": 3.00,
            "default": 1.00,
        },
        validation_alias="AI_MODEL_PRICING_JSON",
    )

    # JWT
    JWT_SECRET_KEY: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Token budgets
    FREE_TIER_DAILY_TOKEN_BUDGET: int = 50_000
    STANDARD_DAILY_TOKEN_BUDGET: int = 200_000

    # AI endpoint rate limits (sliding window, per user)
    AI_ANALYZE_RATE_LIMIT_REQUESTS: int = 5
    AI_ANALYZE_RATE_LIMIT_WINDOW_SECONDS: int = 3600
    AI_GENERATE_RATE_LIMIT_REQUESTS: int = 10
    AI_GENERATE_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # CORS — comma-separated list of origins
    CORS_ORIGINS: str = "http://localhost:3000"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    @field_validator("ai_model_pricing", mode="before")
    @classmethod
    def parse_ai_model_pricing(cls, value: object) -> dict[str, float]:
        if isinstance(value, dict):
            pricing = value
        elif isinstance(value, str):
            pricing = json.loads(value)
        else:
            raise TypeError("AI model pricing must be a JSON object string or dict.")

        if not isinstance(pricing, dict):
            raise TypeError("AI model pricing must decode to an object.")

        normalized: dict[str, float] = {}
        for key, rate in pricing.items():
            if not isinstance(key, str):
                raise TypeError("AI model pricing keys must be strings.")
            normalized[key] = float(rate)
        return normalized

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
