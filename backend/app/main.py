"""CareerCore FastAPI application entry point."""

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG if not settings.is_production else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("CareerCore v%s starting (env=%s)", settings.APP_VERSION, settings.APP_ENV)

    # Check database connectivity
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)

    # Check Redis connectivity
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        logger.info("Redis connection: OK")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)

    yield

    logger.info("CareerCore v%s shutting down", settings.APP_VERSION)
    await engine.dispose()


# ── Application factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="CareerCore API",
        description="AI Career Intelligence Platform",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.exception("Unhandled exception [request_id=%s]: %s", request_id, exc)
        if settings.is_production:
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "request_id": request_id},
            )
        return JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
                "type": type(exc).__name__,
                "request_id": request_id,
            },
        )

    # Routes
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
