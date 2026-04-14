from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


def _build_error_app(app_env: str):
    settings = Settings(
        APP_ENV=app_env,
        APP_VERSION="test-version",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="minioadmin",
        MINIO_SECRET_KEY="minioadmin",
        MINIO_BUCKET="careercore-test",
        CELERY_BROKER_URL="redis://localhost:6379/1",
        CELERY_RESULT_BACKEND="redis://localhost:6379/2",
        JWT_SECRET_KEY="test-secret-key",
        CORS_ORIGINS="http://localhost:3000",
    )
    app = create_app(settings)
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise RuntimeError("kaboom details")

    app.include_router(router, prefix="/test")
    return app


async def test_production_errors_are_generic_and_include_request_id() -> None:
    app = _build_error_app("production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test/boom", headers={"x-request-id": "req-123"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "req-123"
    assert response.json() == {
        "error": "Internal server error",
        "request_id": "req-123",
    }


async def test_development_errors_return_debug_detail() -> None:
    app = _build_error_app("development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test/boom")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "kaboom details"
    assert payload["type"] == "RuntimeError"
    assert payload["request_id"]
    assert response.headers["x-request-id"] == payload["request_id"]
