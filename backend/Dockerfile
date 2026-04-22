# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Source must be present before pip install so setuptools can find the app package.
# A non-editable install copies files into site-packages under /install; the final
# stage then works without the source tree being present at a fixed absolute path.
# (The previous -e "." editable install created a .pth pointing to /build, which
# does not exist in the final image and caused ImportError on startup.)
COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Final ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS final

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (uid 1001)
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Installed packages — includes the app package in site-packages
COPY --from=builder /install /usr/local

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
