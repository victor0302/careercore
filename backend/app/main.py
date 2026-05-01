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
from app.core.config import Settings, get_settings
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
    app_settings: Settings = app.state.settings
    logger.info("CareerCore v%s starting (env=%s)", app_settings.APP_VERSION, app_settings.APP_ENV)

    # Check database connectivity
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)

    # Check Redis connectivity
    try:
        r = aioredis.from_url(app_settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        logger.info("Redis connection: OK")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)

    yield

    logger.info("CareerCore v%s shutting down", app_settings.APP_VERSION)
    await engine.dispose()


# ── Application factory ───────────────────────────────────────────────────────


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or get_settings()
    docs_url = None if app_settings.is_production else "/docs"
    redoc_url = None if app_settings.is_production else "/redoc"
    openapi_url = None if app_settings.is_production else "/openapi.json"

    app = FastAPI(
        title="CareerCore API",
        description="AI Career Intelligence Platform",
        version=app_settings.APP_VERSION,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("Unhandled exception [request_id=%s]: %s", request_id, exc)
        if app.state.settings.is_production:
            response = JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "request_id": request_id},
            )
            response.headers["X-Request-Id"] = request_id
            return response

        response = JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
                "type": type(exc).__name__,
                "request_id": request_id,
            },
        )
        response.headers["X-Request-Id"] = request_id
        return response

    # Routes
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
