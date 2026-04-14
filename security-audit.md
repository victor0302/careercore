# CareerCore Security Audit

**Date:** 2026-04-13  
**Branch:** `security-audit`  
**Scope:** Full codebase — backend, frontend, infrastructure, configuration  
**Auditor:** Claude Code (claude-sonnet-4-6)

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High     | 5 |
| Medium   | 7 |
| Low      | 3 |
| **Total**| **18** |

---

## Critical

---

### C-1 — MinIO Bucket Configured for Anonymous Public Download

**File:** `docker-compose.yml:74`  
**Category:** Docker & Infrastructure Misconfiguration / Data Exposure

**Vulnerability:**  
The `storage_init` container runs the following command to initialize the MinIO bucket:

```sh
mc anonymous set download local/careercore-uploads;
```

This sets the entire `careercore-uploads` bucket to **publicly readable without authentication**. Any person with network access to port 9000 can enumerate and download any user's uploaded files (resumes, documents) by constructing a direct URL — no credentials required.

**Risk:**  
All user-uploaded files are exposed. An attacker who can reach the MinIO port (which is also forwarded to the host on line 56: `"9000:9000"`) can download every resume and document stored by every user.

**Fix:**  
Remove the anonymous policy line entirely. Presigned URLs (already used by `FileService.get_presigned_url()`) are the correct mechanism — they grant time-limited, per-object access without making the bucket public. The bucket should have no anonymous policy.

```sh
# Remove this line from storage_init entrypoint:
mc anonymous set download local/careercore-uploads;
```

---

### C-2 — Hardcoded Credentials Committed to Version Control

**Files:**
- `docker-compose.yml:18` — `POSTGRES_PASSWORD: careercore`
- `docker-compose.yml:51–52` — `MINIO_ROOT_USER: minioadmin`, `MINIO_ROOT_PASSWORD: minioadmin`
- `docker-compose.yml:72` — `mc alias set local http://storage:9000 minioadmin minioadmin`
- `docker-compose.yml:87` — `DATABASE_URL: postgresql+asyncpg://careercore:careercore@db:5432/careercore`
- `docker-compose.yml:114` — Same `DATABASE_URL` repeated in the `worker` service
- `.env.example:13` — `DATABASE_URL=postgresql+asyncpg://careercore:careercore@db:5432/careercore`
- `.env.example:20–21` — `MINIO_ACCESS_KEY=minioadmin`, `MINIO_SECRET_KEY=minioadmin`

**Category:** Secrets & Credentials

**Vulnerability:**  
Actual credentials are hardcoded directly in `docker-compose.yml`, which is committed to the repository. Anyone with read access to the repo can extract the database password and MinIO admin credentials. The `storage_init` entrypoint (line 72) also embeds the credentials directly in a shell command string visible in `docker inspect` output.

`.env.example` reinforces these weak defaults — developers following the example will use identical credentials.

**Risk:**  
If the repository is made public, or an insider threat exists, these credentials give direct access to the PostgreSQL database and all stored files. The `DATABASE_URL` hardcoding in the `backend` and `worker` service environment blocks (lines 87, 114) also overrides any `.env` file setting, meaning even if a developer rotates the password in `.env`, Docker will still use the hardcoded value.

**Fix:**  
- Replace all hardcoded values with variable references in `docker-compose.yml`:

```yaml
db:
  environment:
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_DB: ${POSTGRES_DB}

storage:
  environment:
    MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
    MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}

backend:
  environment:
    DATABASE_URL: ${DATABASE_URL}
```

- Remove the hardcoded `minioadmin minioadmin` from the `storage_init` entrypoint and substitute env vars.
- In `.env.example`, replace all credential values with `CHANGEME` placeholders and add a prominent warning.

---

### C-3 — `FileService.get_for_user()` Does Not Filter by Owner

**File:** `backend/app/services/file_service.py:73–75`  
**Category:** Authentication & Authorization

**Vulnerability:**  
The method is documented as "enforcing ownership" but the implementation ignores the `user_id` parameter entirely:

```python
async def get_for_user(self, user_id: uuid.UUID, file_id: uuid.UUID) -> UploadedFile | None:
    """Return an UploadedFile, enforcing ownership."""
    return await self._db.get(UploadedFile, file_id)  # user_id is unused
```

It fetches any `UploadedFile` by primary key regardless of who owns it. The current file endpoint (`files.py:60`) adds a post-hoc check `record.user_id != current_user.id`, but this is a fragile defense-in-depth: any other call site that trusts the service contract ("enforcing ownership") will silently skip the check.

**Risk:**  
An authenticated user who guesses or obtains another user's `file_id` (a UUID, but not secret by default) can retrieve that file's metadata and generate a presigned download URL for it. This is an Insecure Direct Object Reference (IDOR).

**Fix:**  
Fix the query to actually filter by `user_id`:

```python
async def get_for_user(self, user_id: uuid.UUID, file_id: uuid.UUID) -> UploadedFile | None:
    """Return an UploadedFile only if it belongs to user_id."""
    result = await self._db.execute(
        select(UploadedFile).where(
            UploadedFile.id == file_id,
            UploadedFile.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
```

The redundant check in `files.py:60` can then be removed.

---

## High

---

### H-1 — No Rate Limiting on Authentication Endpoints

**File:** `backend/app/api/v1/endpoints/auth.py:34, 58, 89`  
**Category:** API Security

**Vulnerability:**  
`/register`, `/login`, and `/refresh` have no rate limiting. An attacker can send unlimited requests with no throttling or lockout.

**Risk:**  
- **Brute-force attacks** against `/login` — try millions of password combinations.
- **Email enumeration** — the `register` endpoint returns HTTP 409 for existing emails, allowing an attacker to confirm whether a given email is registered.
- **Credential stuffing** — automated replay of breached credential lists.

**Fix:**  
Add per-IP rate limiting using `slowapi`:

```python
# backend/app/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# auth.py
from app.main import limiter

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...

@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, ...):
    ...

@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(request: Request, ...):
    ...
```

---

### H-2 — Refresh Tokens Are Never Invalidated (Token Reuse Attack)

**File:** `backend/app/services/auth_service.py:63–88`  
**Category:** Authentication & Authorization

**Vulnerability:**  
The `refresh()` method issues a new token pair without invalidating the old refresh token. The code acknowledges this with an explicit TODO at lines 68–70:

```python
# TODO: Implement refresh token rotation — store issued refresh tokens in Redis
# and invalidate the old one when a new pair is issued. This prevents token reuse
# after logout or token theft.
```

There is also no logout endpoint that could invalidate a token.

**Risk:**  
If a refresh token is stolen (e.g., via XSS, network interception on HTTP, or a compromised device), the attacker can use it indefinitely to generate valid access tokens — even after the legitimate user "logs out" on the frontend.

**Fix:**  
Implement refresh token rotation with a Redis allowlist:

1. On login, store the refresh token in Redis with a TTL matching `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.
2. On refresh, check the token exists in Redis before accepting it.
3. Delete the old token from Redis and store the newly issued one.
4. Add a `POST /auth/logout` endpoint that deletes the token from Redis.

```python
async def refresh(self, refresh_token: str) -> TokenPair:
    user_id = decode_refresh_token(refresh_token)  # raises JWTError if invalid

    redis_key = f"refresh_token:{refresh_token}"
    if not await self._redis.exists(redis_key):
        raise AuthError("Refresh token has been revoked or already used.")

    await self._redis.delete(redis_key)

    new_pair = TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
    ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await self._redis.setex(f"refresh_token:{new_pair.refresh_token}", ttl, user_id)
    return new_pair
```

---

### H-3 — CORS Allows All Methods and Headers

**File:** `backend/app/main.py:75–76`  
**Category:** API Security

**Vulnerability:**  

```python
allow_methods=["*"],
allow_headers=["*"],
```

Both are set to wildcard, combined with `allow_credentials=True`.

**Risk:**  
- Allows dangerous HTTP methods like `TRACE`, which can enable Cross-Site Tracing (XST) attacks.
- Per the CORS spec, `allow_credentials=True` with `allow_origins` set to a list of specific origins is acceptable, but the wildcard method/header combination eliminates the precision that makes CORS meaningful as a defense layer.

**Fix:**  
Explicitly enumerate the required methods and headers:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
```

---

### H-4 — Verbose Exception Details Returned in Non-Production Responses

**File:** `backend/app/main.py:89–95`  
**Category:** Error Handling & Information Disclosure

**Vulnerability:**  
The global exception handler returns the raw exception message and Python type name when `APP_ENV != "production"`:

```python
return JSONResponse(
    status_code=500,
    content={
        "error": str(exc),         # raw exception text
        "type": type(exc).__name__, # Python class name
        "request_id": request_id,
    },
)
```

**Risk:**  
If `APP_ENV` is not correctly set to `"production"` in a deployed environment, internal error messages, database query failures, file paths, and Python stack information are returned to clients. This aids reconnaissance. `.env.example:8` defaults to `APP_ENV=development`, making misconfiguration a realistic risk.

**Fix:**  
Add a startup assertion in `create_app()` or `lifespan()` that validates `APP_ENV` against the deployment context, or log a prominent warning:

```python
if settings.is_production:
    logger.warning("APP_ENV is 'development' but DEPLOYMENT_ENV suggests production!")
```

Alternatively, always return the safe response and log the detail server-side only:

```python
logger.exception("Unhandled exception [request_id=%s]", request_id, exc_info=exc)
return JSONResponse(status_code=500, content={"error": "Internal server error", "request_id": request_id})
```

---

### H-5 — Swagger UI Exposed with No Authentication in All Environments

**File:** `backend/app/main.py:65–66`  
**Category:** API Security / Information Disclosure

**Vulnerability:**  

```python
docs_url="/docs",
redoc_url="/redoc",
```

The interactive Swagger UI is enabled unconditionally — including in production. It fully documents every endpoint, schema, request/response format, and parameter, giving an attacker a complete API map.

**Risk:**  
Facilitates reconnaissance and automated attack generation. Attackers can test endpoints directly from the browser without writing any code.

**Fix:**  
Disable docs in production:

```python
app = FastAPI(
    ...
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)
```

---

## Medium

---

### M-1 — MinIO Connection Hardcoded to HTTP (Plaintext in Transit)

**File:** `backend/app/services/file_service.py:19`  
**Category:** Docker & Infrastructure Misconfiguration / Data Exposure

**Vulnerability:**  

```python
endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
```

The S3 client always connects to MinIO over HTTP, even in production. All file uploads and presigned URL generation happen over an unencrypted connection.

**Risk:**  
In any multi-host deployment (backend and MinIO on different machines), file content is transmitted in plaintext over the internal network. This enables passive interception.

**Fix:**  
Make TLS configurable:

```python
protocol = "https" if settings.is_production else "http"
endpoint_url=f"{protocol}://{settings.MINIO_ENDPOINT}",
```

Add `MINIO_USE_TLS=true` to production `.env`.

---

### M-2 — Refresh Token Cookie Path Too Restrictive

**File:** `backend/app/api/v1/endpoints/auth.py:30`  
**Category:** Authentication & Authorization

**Vulnerability:**  

```python
path="/api/v1/auth",
```

The refresh token cookie is only sent by the browser for requests to paths under `/api/v1/auth`. This means the browser will not attach the cookie to requests that need it outside that path (e.g., a dedicated logout endpoint at `/api/v1/auth/logout` would work, but any future token refresh triggered by a 401 interceptor on other endpoints would not receive the cookie).

**Risk:**  
Inconsistent token delivery. Future code that relies on the cookie for automatic token refresh will fail silently, likely forcing developers to use a less secure mechanism (e.g., storing the token in JavaScript-accessible storage).

**Fix:**  
Scope the cookie to the refresh endpoint specifically or to the full API path:

```python
path="/api/v1/auth/refresh",  # most restrictive and correct
```

---

### M-3 — Refresh Token Cookie Not Secure in Development

**File:** `backend/app/api/v1/endpoints/auth.py:27`  
**Category:** Authentication & Authorization

**Vulnerability:**  

```python
secure=settings.is_production,
```

The `Secure` flag is omitted in development. While intentional, if a development server is accessible over a network (e.g., Docker port binding, shared dev machines, CI preview deployments), refresh tokens can be intercepted via HTTP.

**Risk:**  
Token theft via network interception in any non-localhost dev/staging environment.

**Fix:**  
Document this explicitly. Consider enabling `secure=True` whenever the server is not bound to `127.0.0.1`, or add a config check that warns when `APP_ENV=development` but the server is bound to a non-loopback address.

---

### M-4 — File Size Validated After Full Read Into Memory

**File:** `backend/app/api/v1/endpoints/files.py:35–36`  
**Category:** Input Validation & Sanitization

**Vulnerability:**  

```python
data = await file.read()        # entire file buffered first
if len(data) > _MAX_BYTES:      # then checked
    raise HTTPException(...)
```

The entire file body is read into memory before the size check is performed.

**Risk:**  
An attacker can upload a multi-gigabyte file, consuming server RAM and potentially causing an out-of-memory crash (DoS). The `_MAX_BYTES = 10 * 1024 * 1024` limit is never enforced at the stream level.

**Fix:**  
Check the `Content-Length` header before reading and enforce a streaming cap:

```python
content_length = request.headers.get("content-length")
if content_length and int(content_length) > _MAX_BYTES:
    raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

data = await file.read(_MAX_BYTES + 1)  # read one byte past limit
if len(data) > _MAX_BYTES:
    raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")
```

---

### M-5 — Missing `GET /auth/me` Endpoint

**File:** `backend/app/api/v1/router.py` / `backend/app/api/v1/endpoints/auth.py`  
**Category:** Authentication & Authorization

**Vulnerability:**  
The frontend `useAuth` hook calls `GET /api/v1/auth/me` to retrieve the current user after login, but this endpoint is not defined anywhere in the backend router. The auth router only exposes `/register`, `/login`, and `/refresh`.

**Risk:**  
The frontend authentication flow is broken. After login, the app cannot retrieve the authenticated user's identity, likely causing repeated login loops or a broken session state.

**Fix:**  
Add the endpoint to `auth.py`:

```python
from app.core.dependencies import get_current_user

@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
```

---

### M-6 — AI Budget Not Checked Before AI Calls

**File:** `backend/app/services/job_service.py:57–62`  
**Category:** API Security / Data Exposure

**Vulnerability:**  
`JobService.parse()` has an explicit TODO acknowledging that `AICostService.check_budget()` is not called before invoking the AI provider:

```python
# TODO:
#   1. Check AICostService.check_budget() before calling AI.
#   ...
#   4. Call AICostService.log_call() with token counts.
```

The current implementation skips all of this and just sets `parsed_at`:

```python
job.parsed_at = datetime.now(tz=timezone.utc)
await self._db.flush()
return job
```

**Risk:**  
- Users can trigger unlimited AI calls regardless of their tier, generating unbounded cost.
- AI calls are not logged in `AICallLog`, breaking cost accountability and the ability to detect abuse.

**Fix:**  
Implement the full flow as documented in the method's TODO block, wiring `AICostService.check_budget()` before the provider call and `AICostService.log_call()` after.

---

### M-7 — No Security Headers

**File:** `backend/app/main.py`  
**Category:** API Security

**Vulnerability:**  
The application does not set any of the standard defensive HTTP security headers.

**Risk:**  
Missing headers reduce defense-in-depth. Relevant absent headers:
- `X-Content-Type-Options: nosniff` — prevents MIME sniffing
- `X-Frame-Options: DENY` — prevents clickjacking
- `Strict-Transport-Security` — enforces HTTPS
- `Cache-Control: no-store` — prevents caching of sensitive API responses

**Fix:**  
Add a middleware that injects these headers on every response:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response
```

---

## Low

---

### L-1 — Minimum Password Length of 8 Characters

**File:** `backend/app/schemas/user.py:10`  
**Category:** Authentication & Authorization

**Vulnerability:**  

```python
password: str = Field(min_length=8, max_length=128)
```

8 characters is below current guidance. NIST SP 800-63B recommends a minimum of 8 but encourages 12+, and most modern frameworks recommend at least 12.

**Fix:**  
Increase to 12:

```python
password: str = Field(min_length=12, max_length=128)
```

---

### L-2 — Weak/Placeholder JWT Secret in `.env.example`

**File:** `.env.example:37`  
**Category:** Secrets & Credentials

**Vulnerability:**  

```
JWT_SECRET_KEY=replace-me-with-a-secure-random-hex-string
```

No minimum length or format is enforced by `config.py`. A developer who copies `.env.example` without changing this value will run with a trivially guessable secret.

**Risk:**  
A weak JWT secret allows an attacker to brute-force or forge valid JWT tokens, granting arbitrary account access.

**Fix:**  
Add a validator in `config.py` that enforces a minimum key length:

```python
@field_validator("JWT_SECRET_KEY")
@classmethod
def validate_jwt_secret(cls, v: str) -> str:
    if len(v) < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters (use token_hex(32))")
    if v == "replace-me-with-a-secure-random-hex-string":
        raise ValueError("JWT_SECRET_KEY has not been changed from the example value")
    return v
```

---

### L-3 — File Text Extraction Celery Task Is a Stub

**File:** `backend/app/workers/tasks/extraction_tasks.py:42–43`  
**Category:** Data Exposure / Error Handling

**Vulnerability:**  

```python
# Stub — not yet implemented
return {"file_id": file_id, "status": "not_implemented", "chars_extracted": 0}
```

The task always returns `"status": "not_implemented"` and never sets `UploadedFile.status = FileStatus.ready`. Files will remain in `FileStatus.pending` permanently with no error surfaced to the user.

**Risk:**  
- Silent feature failure — users upload documents but can never use them for resume/job analysis.
- Files consume MinIO storage with no lifecycle management (no retry, no error state, no expiry).
- Celery task queue fills with tasks that complete "successfully" but do nothing.

**Fix:**  
Implement the task as specified in the module docstring (lines 1–16), or at minimum make the stub set `FileStatus.error` with an `error_message` so failures are visible:

```python
# Temporary stub that honestly reports its state
record.status = FileStatus.error
record.error_message = "Text extraction not yet implemented"
await session.commit()
return {"file_id": file_id, "status": "error", "chars_extracted": 0}
```

---

## Immediate Action Items

The following should be addressed before any production deployment or public repository access:

1. **C-1** — Remove `mc anonymous set download` from `docker-compose.yml` (files are publicly accessible right now)
2. **C-2** — Replace all hardcoded credentials in `docker-compose.yml` with environment variable references
3. **C-3** — Fix `FileService.get_for_user()` to filter by `user_id` in the SQL query
4. **H-1** — Add rate limiting to `/login`, `/register`, and `/refresh`
5. **H-2** — Implement refresh token rotation via Redis; add a logout endpoint
6. **H-5** — Disable Swagger UI in production (`docs_url=None`)
7. **M-5** — Add the missing `GET /auth/me` endpoint
