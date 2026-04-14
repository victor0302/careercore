# CareerCore — Engineering Notes

_Written as a reference for understanding every structural and architectural decision
made in the Phase 1 scaffold. Read this once before writing your first line of
application logic._

---

## How to read this document

Each section answers one question: **why does this exist, and why does it look
the way it does?** The goal is not to describe what a file does — you can read
the code for that. The goal is to explain the reasoning behind every decision,
so you can make consistent choices when adding new code.

---

## 1. Top-level layout

```
careercore/
├── backend/
├── frontend/
├── cli/
├── infra/
├── docs/
└── .github/
```

**Why a monorepo?**

A monorepo means one `git clone`, one PR, one CI run. For a small team (or solo
capstone project), the overhead of managing multiple repos — syncing schemas,
coordinating releases, juggling separate CI configs — is not worth it. When you
change a Pydantic schema in the backend, you update the matching TypeScript
interface in the same commit and the reviewer sees both changes at once.

The tradeoff is that CI takes longer because it runs both backend and frontend
checks on every PR. That is acceptable here, and mitigated by running jobs in
parallel and only running Docker builds after tests pass.

**Why separate `backend/`, `frontend/`, `cli/`, `infra/`?**

Each directory is a deployable unit with its own runtime, dependencies, and
Dockerfile. They are co-located for convenience, not because they share code.
No Python is imported by the frontend. No TypeScript is imported by the backend.
This boundary is enforced by the fact that they are completely different
language runtimes.

`docs/` is not a deployable unit — it is the design corpus. Keeping it in the
repo means design decisions travel with the code, are versioned, and appear in
PRs when updated.

`infra/` contains Terraform and helper scripts. It is separate from `backend/`
because infrastructure configuration has a different change cadence and a
different audience (ops vs. developers). You do not want a backend developer
accidentally running `terraform apply` while fixing a bug.

---

## 2. `.env.example` and secrets discipline

**Why does `.env.example` exist at all?**

It is the single source of truth for every environment variable the application
needs. When a new developer joins, they run `cp .env.example .env` and know
exactly what to fill in. When a new variable is added, the `.env.example` must
be updated in the same PR — otherwise the next person to pull will have a
broken environment with no error message that explains why.

**Why not just document variables in the README?**

Because README docs go stale. A file that is `cp`'d and sourced by the
application is automatically correct. If you add a variable to the code but
forget to add it to `.env.example`, CI will catch it because the CI environment
only has what is in `.env.example`.

**Why are there comments and example (non-secret) values?**

Because a field called `JWT_SECRET_KEY=` with no comment is useless. The
comment says how to generate a valid value. The example value shows the format.
This is the difference between a config file that helps people and one that
frustrates them.

**The rule:** Nothing in `.env.example` should ever be a real secret. Strings
like `sk-ant-replace-me` are obviously placeholders. `minioadmin` is the MinIO
default and is safe to commit because it only works on a local MinIO instance
with no internet exposure.

---

## 3. `docker-compose.yml` design

**Service topology:**

```
frontend (3000) ─┐
backend  (8000) ─┤── careercore-net (bridge)
worker          ─┤
db     (internal)┤
redis  (internal)┤
storage (9000)  ─┘
storage_init    ──► exits after bucket creation
```

**Why is `db` not exposed to the host?**

PostgreSQL should never be directly reachable from outside the Docker network.
In local development it seems convenient, but it creates a habit of connecting
to production databases directly, which is dangerous. If you need to inspect the
database, use `docker compose exec db psql` or a tunneled connection.

**Why `depends_on` with `condition: service_healthy`?**

Without health checks, Docker Compose starts services in dependency order but
does not wait for them to be ready. The backend starting before Postgres is
ready will crash with a connection error on its first DB query. `service_healthy`
means "wait until the health check passes" — which for Postgres means
`pg_isready` returns success, i.e., it is actually accepting connections.

**Why a separate `storage_init` service?**

MinIO starts without any buckets. The application assumes the bucket exists.
Rather than adding bucket-creation code to the backend startup (which would
couple application code to infrastructure concerns), we use a one-shot
`mc` (MinIO client) container that creates the bucket and exits. This is the
same pattern used by `db-migrate` containers in production deployments —
a disposable init job that runs once.

**Why `worker` depends on `backend` and not directly on `db` + `redis`?**

The Celery worker imports the same application code as the backend. If the
backend starts successfully, it means the dependencies (config, models, etc.)
are importable. This is a soft dependency, not a technical one — in production
you would depend on `db` and `redis` directly. But for local dev it is simpler.

**Why named volumes instead of bind mounts for db/redis/minio?**

Named volumes (`postgres_data`, `redis_data`, `minio_data`) survive
`docker compose down` but are removed by `docker compose down -v`. This means
your local database persists across restarts (useful for development) but you
can nuke it intentionally. Bind mounts (e.g., `./data/postgres:/var/lib/...`)
would work too, but they create directories in your repo that get accidentally
committed or have permission issues on different OSes.

---

## 4. GitHub Actions workflow architecture

**`ci.yml` — ordered by fail-fast cost**

```
lint-python → typecheck-python → test-backend
lint-frontend → typecheck-frontend → test-frontend
security-scan
docker-build (only runs after test-backend + test-frontend)
```

Jobs run in this order intentionally. Lint fails in seconds and is cheap to
run first. Type checking is slower but catches structural errors before you spin
up test databases. Tests are slowest and require service containers. Docker
builds are the most expensive and only run when tests pass.

`AI_PROVIDER=mock` is set at the workflow level, not inside individual jobs.
This ensures no job can accidentally call a real AI API, regardless of what
`secrets.ANTHROPIC_API_KEY` is set to.

**`cd.yml` — push to main only**

CD only triggers on `push` to `main`, not on `pull_request`. This is the
standard separation: CI validates PRs, CD deploys merges. The deploy job uses
`environment: development` which maps to a GitHub environment with its own
secrets and protection rules. You can add a required reviewer to the `production`
environment later.

**`security.yml` — scheduled, not per-PR**

Dependency audits and image scans run weekly rather than on every PR because:
1. New vulnerabilities are discovered continuously — a PR that was clean
   yesterday might be flagged today through no change of your own.
2. Full dependency audits are slow and the results are the same whether you run
   them 50 times per day or once per week.
3. `gitleaks` with `fetch-depth: 0` scans the full git history and is expensive.
   You want it on a schedule, not on every commit.

---

## 5. Backend structure deep-dive

### 5.1 `app/` layout

```
app/
├── main.py          — FastAPI app factory + lifespan
├── core/            — Config, security, dependency injection
├── db/              — SQLAlchemy engine + session + base models
├── models/          — Database table definitions (SQLAlchemy ORM)
├── schemas/         — API request/response shapes (Pydantic)
├── ai/              — AI provider abstraction layer
├── services/        — Business logic (no HTTP concerns)
├── api/             — HTTP routing + endpoint handlers
└── workers/         — Celery app + async task definitions
```

**Why separate `models/` from `schemas/`?**

This is one of the most important structural decisions in a FastAPI app.

`models/` contains SQLAlchemy classes — they define what is in the database.
They have relationships, lazy-loading behavior, and SQLAlchemy-specific types.

`schemas/` contains Pydantic classes — they define what the API accepts and
returns. They are serializable, validated, and independent of the database.

They are not the same thing, even when they look similar. A SQLAlchemy `User`
model has a `password_hash` field. The Pydantic `UserRead` schema does not —
you never send a password hash over the wire. A `WorkExperience` model has
relationships to `Profile` and `UploadedFile`. The `WorkExperienceRead` schema
has `profile_id: uuid.UUID` — a simple foreign key value, not a nested object.

If you merge them (as some tutorials do), you end up with schemas that leak
internal fields, relationships that cause N+1 queries when serialized, and
circular import nightmares. Keep them separate.

**Why `services/` instead of putting logic in endpoints?**

Services are where business logic lives. Endpoints are where HTTP contracts are
defined. Mixing them means you cannot test business logic without spinning up
an HTTP server, and it becomes impossible to reuse logic across endpoints
(e.g., `auth_service.register()` is called from the REST endpoint today, and
from a CLI command in Phase 2).

The pattern is:
```
endpoint receives HTTP request
→ validates input with Pydantic schema
→ delegates to service
→ service does business logic
→ service uses models (DB) and AI provider as needed
→ returns domain object or raises domain exception
→ endpoint converts to HTTP response or maps exception to HTTP status code
```

This separation means:
- Services are unit-testable without HTTP overhead
- Endpoints stay thin and readable
- Business logic is reusable from CLI, Celery tasks, or other services

### 5.2 `app/core/`

**`config.py` — pydantic-settings singleton**

`Settings` reads from environment variables. `@lru_cache` means the Settings
object is constructed exactly once per process. Every import of `get_settings()`
returns the same object — no repeated env reads, no repeated validation.

Why `lru_cache` instead of a module-level global? Because module-level globals
are instantiated at import time, which breaks tests that need to override env
vars before importing the module. With `lru_cache`, you can `get_settings.cache_clear()`
in test setup and the next call reads fresh env vars.

**`security.py` — pure functions, no state**

Security functions (hashing, JWT creation/validation) are pure functions with
no side effects and no database access. This makes them trivially testable and
reusable. Notice they do not import anything from `app.db` or `app.models` —
that would be a layering violation.

**`dependencies.py` — FastAPI dependency injection**

`get_current_user` is the authentication gate for every protected endpoint.
It is implemented as a FastAPI dependency (not middleware) because:
1. It yields the authenticated user object into the endpoint's scope
2. Individual endpoints can opt out by simply not declaring it as a parameter
3. It integrates with FastAPI's OpenAPI generation (shows the padlock in /docs)
4. It is testable by overriding with `app.dependency_overrides`

The function raises `HTTP 401` with `WWW-Authenticate: Bearer` header — this is
the correct response per RFC 6750. Do not return 403 for missing/invalid tokens;
403 means "authenticated but not authorized."

### 5.3 `app/db/`

**`base.py` — mixins over inheritance chains**

`UUIDPrimaryKeyMixin` and `TimestampMixin` are Python mixins, not a base class
with all functionality. Every model gets a UUID primary key and `created_at`/
`updated_at` timestamps — but through composition, not deep inheritance.

Why UUIDs instead of auto-increment integers?

- UUIDs are globally unique — you can generate them before inserting, which
  simplifies multi-step operations and event sourcing.
- They do not leak information about record count or insert order.
- They work across distributed systems without coordination.
- They make it harder to IDOR (insecure direct object reference) — guessing
  `/jobs/1`, `/jobs/2`, `/jobs/3` is trivially easy with integers.

Why `server_default=func.gen_random_uuid()` in addition to `default=uuid.uuid4`?

The Python `default` fires when you create an object in Python code. The
`server_default` fires when you insert a row with a raw SQL statement (e.g.,
in a data migration or a test seed script). Both should produce UUIDs.

**`session.py` — async engine with proper lifecycle**

`get_db` is a generator that yields a session and commits or rolls back when
done. The `try/except/finally` block ensures:
- Success path: commit happens automatically (no need to call `await db.commit()`
  in every endpoint)
- Error path: rollback happens automatically (prevents dirty state from leaking
  into the next request)
- Always: session is closed (prevents connection pool exhaustion)

`pool_pre_ping=True` means SQLAlchemy sends a `SELECT 1` before using a pooled
connection. Without this, a stale connection (dropped by the DB after being idle)
will cause the first query in a request to fail.

### 5.4 `app/models/` — 13 model files

**Why one model per file, not all in one file?**

At 13 models, a single `models.py` file would be 600+ lines. More importantly,
relationships between models create circular dependencies when everything is in
one file. The solution used here is:
1. Each model file imports only what it needs at the top
2. Forward-reference strings (`"Profile"`, `"User"`) break import-time circular
   deps for `relationship()`
3. Bottom-of-file imports bring in the referenced models so Python can resolve
   the strings at runtime

This is the standard pattern for SQLAlchemy models in large applications.

**Why `__init__.py` imports all models?**

Alembic's `env.py` imports `app.models` (the package). For Alembic to detect
all tables and generate correct migrations, every model class must be imported
before `Base.metadata` is inspected. The `__init__.py` does exactly that —
one import statement in `env.py` causes all 13 models to be registered.

If you add a new model and forget to add it to `__init__.py`, Alembic will not
know it exists and will not generate a migration for it. This is a common
mistake — the `__init__.py` is the registration mechanism.

**`ai_call_log.py` — why no FK to User?**

`AICallLog.user_id` is not a foreign key. This is intentional. If a user
deletes their account, their AI call logs must be retained for billing, auditing,
and fraud detection. A foreign key with `ON DELETE CASCADE` would destroy that
history. A foreign key with `ON DELETE SET NULL` would lose the user association.
Not having a foreign key means the log is a fact about an event that happened
— it does not depend on the continued existence of the user.

**`audit_log.py` — the append-only table**

The audit log is the most important table in the system from a compliance
perspective. It records everything that changed, who changed it, and when.
Two rules apply:
1. No `UPDATE` or `DELETE` statements on this table — ever. Application code
   must not have this capability.
2. Every state-changing operation (create, update, delete, login, upload)
   must write to this table via `AuditService.log_event()`.

The enforcement mechanism is code review + the `AuditService` abstraction.
In Phase 2, add a Postgres role with `INSERT`-only permissions on `audit_logs`
and use that role for the application connection.

### 5.5 `app/ai/` — the provider abstraction

**Why a `Protocol` instead of an abstract base class?**

Python's `Protocol` (from `typing`) enables structural subtyping — "duck typing
with type checking." Any class that implements the required methods satisfies
the protocol, without inheriting from it. This means:

- `MockAIProvider` does not need to import `AIProvider` to satisfy it
- Third-party AI client classes could satisfy it without modification
- `isinstance(obj, AIProvider)` works at runtime because of `runtime_checkable`

An abstract base class (ABC) would require every provider to inherit from it,
creating coupling between the interface and the implementation. A Protocol
decouples them.

**Why four providers when only two work?**

The provider enum already encodes the roadmap: `mock` → `anthropic` (Phase 1),
`openai_compatible` (Phase 2), `ollama` (Phase 3). The stubs exist so that:
1. The interface is stable — adding a new provider means implementing methods,
   not changing the interface
2. Phase 2 and Phase 3 contributors know exactly what they need to implement
3. `get_ai_provider()` can be extended without refactoring call sites

**Why `lru_cache` on `get_ai_provider()`?**

The provider is stateful (it holds an HTTP client). You want one instance per
process, not one per request. `lru_cache(maxsize=1)` gives you a singleton
without a global variable.

**Model selection in `AnthropicProvider`:**

- `parse_job_description` and `explain_score` use Haiku (fast, cheap, structured
  output tasks)
- `generate_bullets`, `answer_followup`, `generate_recommendations`,
  `generate_learning_plan` use Sonnet (higher reasoning quality, longer context)

This is a deliberate cost/quality tradeoff. Parsing a JD into JSON is a simple
extraction task — Haiku handles it correctly at 12× lower cost than Sonnet.
Generating resume bullets requires nuance, evidence selection, and writing
quality — Sonnet earns its cost here.

**`ai/schemas.py` vs `schemas/`:**

`schemas/` contains API-facing Pydantic models — what the HTTP endpoints accept
and return. `ai/schemas.py` contains AI-internal Pydantic models — the typed
contracts between the services and the AI provider. These are never serialized
to HTTP responses directly; they are intermediate data structures. Keeping them
in `ai/` scopes them correctly.

### 5.6 `app/services/`

**`scoring_service.py` — the most important service**

The scoring service is intentionally deterministic. It never calls an LLM.
This matters for several reasons:

1. **Testability:** Deterministic logic can be exhaustively unit tested. LLM
   calls cannot — the output varies by model version, temperature, and prompt.
2. **Cost:** Scoring happens on every analysis. If scoring required an LLM call,
   every job analysis would consume tokens just to get a number.
3. **Explainability:** A weighted formula with an evidence map is auditable.
   "You scored 72/100 because you matched 7/10 skill requirements, 2/5
   experience requirements..." is something a user can understand and contest.
   An LLM-generated score is a black box.

The weight formula (skills 35%, experience 20%, projects 20%, tools 10%,
education 10%, bonus 5%) reflects the empirical reality of technical job
screening: skills and experience dominate, projects demonstrate practical
application, tools are a tiebreaker.

**`ai_cost_service.py` — budget before every call**

Every AI call has two mandatory bookends:
```
check_budget(user) → make AI call → log_call(...)
```

`check_budget` reads today's token usage from `ai_call_logs` and raises
`BudgetExceededError` if the user is over their daily limit. This happens before
the call — you do not want to make a $0.10 API call and then discover the user
was over budget.

`log_call` writes an `AICallLog` row after every call, success or failure. You
need to log failures too — if the API is down and every call fails, you still
want a record of the attempts for debugging.

The TODO comment about Redis caching is important: querying the DB for token
usage on every AI call is a N+1 problem at scale. The fix is to cache
`(user_id, date)` → `total_tokens` in Redis with a TTL. Phase 1 uses the
simpler DB query.

**`audit_service.py` — the append gate**

`AuditService.log_event()` is the only way application code should write to
`audit_logs`. Calling `db.add(AuditLog(...))` directly in an endpoint is
technically possible, but bypasses the service interface that future developers
expect. By routing all writes through the service, you have one place to add
enrichment (e.g., adding geolocation from the IP in Phase 2).

Note that `log_event` calls `await db.flush()`, not `await db.commit()`. The
caller owns the transaction. If the caller's operation fails and rolls back,
the audit log entry rolls back too — which is correct, because a failed
operation should not appear in the audit log.

### 5.7 `app/api/v1/`

**Why version the API at `/api/v1/`?**

Because you will eventually need to change a response shape, rename a field,
or restructure an endpoint in a way that would break existing clients. With
versioning, you can keep `/api/v1/` stable and introduce `/api/v2/` alongside
it, giving clients time to migrate.

`/api/` as a prefix separates API routes from any future server-rendered pages
or static files served from the same host.

**Why `router.py` as an aggregator?**

`main.py` should not know about individual endpoint modules. `router.py` is the
single import point for all v1 routes. When you add a new endpoint file, you
add one line to `router.py` and one test file — no other files change.

**Endpoint ownership enforcement:**

Every endpoint that accesses user data must verify ownership. The pattern is:
```python
# CORRECT: filter by both ID and user_id
result = await db.execute(
    select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
)
# WRONG: only filter by ID — lets any authenticated user access any job
result = await db.execute(select(Job).where(Job.id == job_id))
```

The second form is an IDOR vulnerability (Insecure Direct Object Reference).
Every `get_for_user()` method in the service layer enforces this double filter.

### 5.8 `app/workers/`

**Why Celery for background tasks?**

File text extraction is I/O-bound and can take 10-30 seconds for large PDFs.
You do not want an HTTP request to block for 30 seconds. Celery offloads the
work to a background worker process. The request returns immediately with
`{"status": "pending"}`, and the client polls (or receives a webhook in Phase 2)
when extraction is complete.

**Two queues: `default` and `ai_tasks`**

In Phase 2, AI-heavy tasks (bullet generation, job parsing) will go into
`ai_tasks`. This allows you to scale AI workers independently from file
extraction workers. A file extraction worker needs disk I/O capacity. An AI
task worker needs network I/O capacity for API calls. Different bottlenecks →
different scaling profiles.

**`task_acks_late=True`**

By default, Celery acknowledges (removes from queue) a task as soon as a worker
picks it up. If the worker crashes mid-execution, the task is lost.
`acks_late=True` means the task is only acknowledged after it completes
successfully. If the worker crashes, the task returns to the queue and is
retried. Essential for file extraction — you cannot lose a user's upload.

### 5.9 `alembic/env.py`

**Why async engine in Alembic?**

The application uses async SQLAlchemy. Alembic's default `env.py` uses a sync
engine. If you use a sync engine for migrations, you cannot use
`asyncpg` as the driver (asyncpg is async-only). The solution is to run
`asyncio.run(run_async_migrations())` in the online migration function —
Alembic's sync wrapper calls an async function internally.

**Why import `app.models` in `env.py`?**

`Base.metadata` only contains table definitions for models that have been
imported into the Python process. If you run `alembic autogenerate` without
importing all models, it will see an empty metadata and generate a migration
that drops all your tables (because it thinks they are "extra" tables not in
the metadata). The `import app.models` line triggers the side-effect imports
that populate the metadata.

### 5.10 `tests/conftest.py`

**Why SQLite for unit tests?**

PostgreSQL-specific tests (integration tests) require a running PostgreSQL
instance. For pure unit tests (testing scoring logic, auth service, etc.),
SQLite in-memory is faster to start, requires no external services, and is
destroyed after each test. This lets you run the unit test suite offline, in
CI without service containers, or on a slow laptop.

The tradeoff: SQLite does not support JSONB, ARRAY, or some PostgreSQL-specific
constraints. Unit tests that involve those column types need to use PostgreSQL.
The conftest is designed to switch: set `DATABASE_URL` to a PostgreSQL URL for
integration tests.

**Why `scope="session"` for `test_engine` but no scope for `db`?**

The engine (connection pool setup) is created once per test session — expensive
to recreate. The session is created per test with a rollback at the end — cheap,
and it ensures test isolation. Each test gets a clean slice of the database
because the rollback undoes all inserts, updates, and deletes made during
that test.

**`app.dependency_overrides` — the correct way to mock in FastAPI tests**

FastAPI's dependency injection system is designed for testability. Instead of
monkey-patching, you replace the dependency function directly:
```python
app.dependency_overrides[get_db] = lambda: db
app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
```

After the test, `app.dependency_overrides.clear()` restores the originals.
This is cleaner than mocking because it works the same way in tests as in
production — the dependency system is exercised, not bypassed.

---

## 6. Frontend structure

```
src/
├── app/          — Next.js App Router pages (route = file system path)
├── components/   — Reusable UI components
├── hooks/        — Custom React hooks (encapsulate stateful logic)
├── lib/          — Pure utility functions (api client, auth helpers)
└── types/        — TypeScript interfaces shared across the app
```

**Why App Router (Next.js 14) instead of Pages Router?**

App Router is the current direction of Next.js. It enables:
- React Server Components (no client bundle for static content)
- Nested layouts without prop drilling
- Streaming and Suspense boundaries
- Simpler data fetching patterns

For a green-field project in 2026, using the Pages Router would be
accumulating technical debt on day one.

**`src/lib/api.ts` — the typed fetch wrapper**

Every API call goes through `api.get()`, `api.post()`, etc. This means:
1. The `Authorization: Bearer` header is attached in one place, not scattered
   across 20 component files
2. The 401 → refresh → retry logic is in one place
3. `ApiRequestError` gives you a typed error class you can `instanceof` check
4. Changing the base URL (e.g., for different environments) is one-line change

Without this wrapper, you end up with `fetch(...)` calls in components that
each handle authentication differently, or not at all.

**`src/lib/auth.ts` — token storage isolated**

All token reads and writes go through `getAccessToken()`, `setTokenPair()`,
`clearTokens()`. If you later decide to move from localStorage to httpOnly
cookies (the correct production approach), you change this one file. No
component needs to know where tokens are stored.

The `if (typeof window === "undefined") return null` guards are necessary
because Next.js renders components server-side, where `localStorage` does not
exist. Calling `localStorage.getItem()` on the server throws a ReferenceError.

**`src/hooks/useAuth.ts`**

`useAuth` encapsulates the "am I logged in?" state. Components that need the
current user call `const { user, isAuthenticated } = useAuth()` rather than
reading localStorage directly. This means:
1. Auth state is centralized — one source of truth
2. Components re-render when auth state changes (logout triggers redirect)
3. The loading state prevents flash-of-unauthenticated-content

**`src/types/index.ts` — TypeScript interfaces**

These mirror the backend Pydantic schemas. They are not auto-generated (Phase 2
could add `openapi-typescript` for that). Keeping them in one file makes them
easy to keep in sync — when you change a backend schema, you grep for the
corresponding interface and update it in the same PR.

**Why TanStack Query?**

TanStack Query handles the cache layer between the API and React components:
- Deduplicates concurrent requests for the same data
- Caches responses and serves them instantly on re-renders
- Handles loading and error states with a consistent API
- Provides background refetching so data stays fresh
- Invalidates cache entries when mutations succeed

The alternative — `useEffect` + `useState` + manual fetch — works but produces
repetitive, error-prone code in every component that needs remote data.

---

## 7. CI/CD design decisions

**Why `pip-audit` instead of Dependabot?**

Dependabot opens PRs automatically. `pip-audit` in CI blocks the build if a
vulnerability is found. Both are useful. `pip-audit` catches vulnerabilities
that exist in the current codebase right now, not just new additions.

**Why `gitleaks`?**

Gitleaks scans git history for secrets. If a developer accidentally commits an
API key and then makes a "remove secret" commit, the secret is still in the
history. Gitleaks catches this. It runs on `fetch-depth: 0` (full history) in
the scheduled scan, and on the PR's diff in CI.

**Why Trivy for image scanning?**

Trivy scans container images for known CVEs in the OS packages and language
dependencies. An image built from `python:3.12-slim` might contain a vulnerable
version of `openssl` or `zlib`. Trivy catches this before the image is deployed.

---

## 8. Security decisions

**JWT access + refresh token split**

Access tokens expire in 15 minutes. Refresh tokens expire in 7 days. This
design means:
- If an access token is stolen, the attacker has 15 minutes before it expires.
- The frontend automatically refreshes before expiry — users do not get logged out.
- If a refresh token is stolen (more serious), the user's password change or
  logout invalidates it (Phase 2: store issued refresh tokens in Redis and
  invalidate on use).

**bcrypt for password hashing**

bcrypt is the correct choice for password hashing in 2026. It is adaptive
(cost factor can be increased as hardware improves), salted by design, and
well-supported. Do not use SHA-256, MD5, or any non-adaptive hash for passwords.

**Non-root containers**

Both Dockerfiles create a user with UID 1001 and run the process as that user.
If the container is compromised, the attacker runs as UID 1001, not root. On
the host, UID 1001 has no special privileges. This does not prevent all attacks,
but it is a meaningful reduction in blast radius.

**Ownership checks on every endpoint**

Every endpoint that reads or modifies user data filters by `user_id = current_user.id`.
This prevents IDOR vulnerabilities where an authenticated user can access
another user's data by guessing or enumerating UUIDs.

---

## 9. What is NOT in Phase 1 and why

**Email verification:** Requires an email service (SES, SendGrid, etc.) and
increases deployment complexity. Phase 1 assumes a trusted local environment.
Add it before opening public registration.

**Refresh token rotation (Redis-backed):** The current implementation issues
new refresh tokens but does not invalidate old ones. This means a stolen refresh
token remains valid until it expires. The fix (store issued tokens in Redis,
invalidate on use) is documented as a TODO and is a Phase 2 requirement before
production.

**Rate limiting:** The API has no rate limiting. Add this via Redis-backed
middleware (e.g., `slowapi`) before any public deployment. Without it, a single
client can exhaust your AI token budget.

**HTTPS termination:** The Compose setup exposes HTTP. Production requires TLS.
Use a reverse proxy (Nginx, Caddy, or a cloud load balancer) to terminate TLS
in front of the backend and frontend.

**Pagination:** All list endpoints return all results. For small datasets this
is fine. When a user has 200 job descriptions, you need `limit`/`offset` or
cursor-based pagination. This should be added in the first real sprint.

---

## 10. The right way to add a new feature

Following the existing patterns:

1. **Add the model** in `app/models/your_model.py`. Import it in
   `app/models/__init__.py`. Run `alembic revision --autogenerate`.

2. **Add Pydantic schemas** in `app/schemas/your_schema.py` for API I/O.

3. **Add a service** in `app/services/your_service.py` with async methods.
   Business logic goes here, not in endpoints.

4. **Add endpoints** in `app/api/v1/endpoints/your_endpoint.py`. Register
   the router in `app/api/v1/router.py`.

5. **Write tests** in `backend/tests/`. Unit tests for the service. Integration
   tests (if needed) for the endpoint using the async client fixture.

6. **Add TypeScript types** to `frontend/src/types/index.ts`.

7. **Add API calls** to `frontend/src/lib/api.ts` or a domain-specific lib file.

8. **Wire up the UI** in the appropriate page or component.

Every new endpoint must:
- Filter by `user_id = current_user.id` for owned resources
- Write to the audit log for state-changing operations
- Check `AICostService.check_budget()` before any AI call
- Use `MockAIProvider` in all tests (`AI_PROVIDER=mock`)

---

## 11. Delivery workflow we established

This section documents the operating workflow used to turn the scaffold into a
real team project. These are not administrative details. They are part of the
engineering system because they determine whether future changes are reviewable,
isolated, and safe to merge.

### 11.1 Why the repo had to be bootstrapped before feature work

The local `careercore/` directory initially was **not** a git repository.
Until that was fixed, there was no meaningful way to do feature branches or PRs.

The first sequence was:
1. Initialize git locally
2. Create the GitHub repo
3. Create and push `main`
4. Commit the scaffold as the baseline

Why do this before touching tickets?

Because feature work only makes sense relative to a stable base. If you do
"initial import + feature implementation" in the same history step, you destroy
the review boundary. Reviewers cannot tell what belongs to the system baseline
and what belongs to the new feature.

The rule is:

```
baseline first
→ ticket branch second
→ narrow PR third
```

### 11.2 Why the issue backlog was normalized before implementation

The original ticket list described the product reasonably well, but parts of it
did not match the codebase exactly.

Examples:
- The code used `Profile`, while some draft ticket wording still said `MasterProfile`
- The AI provider contract already used `answer_followup` and
  `generate_recommendations`
- Some files already existed, so the real work was "finish and harden" rather
  than "create from scratch"

Why normalize this instead of leaving it alone?

Because issues are the team's shared vocabulary. If the tracker and the code
use different terms, the project splits into two mental models. That creates
misnamed branches, confusing PRs, and duplicated work.

Normalizing the backlog aligned:
- GitHub issues
- branch names
- PR titles
- code terminology
- review expectations

This is a high-leverage move because once the tracker is clean, all downstream
communication gets cleaner too.

### 11.3 Why GitHub Projects was kept deliberately small

The `CareerCore Phase 1` project board was created with:
- the default `Status` field
- one added `Priority` field with `P1`, `P2`, `P3`

Why not build a complex workflow?

Because small teams do not fail from lack of tooling sophistication; they fail
from inconsistent execution. A board with too many custom fields becomes stale
because nobody wants to maintain it. A small board gets used.

The chosen board answers only the two questions that matter most:
- What stage is this in?
- What should we pull next?

That is enough for a capstone team.

### 11.4 The issue execution workflow

For every ticket, the operating sequence became:

1. Confirm dependent PRs are merged
2. Update local `main` from GitHub
3. Assign the issue
4. Move it to `In Progress`
5. Create a dedicated branch from `main`
6. Implement only the issue scope
7. Run the best available checks
8. Commit with a narrow message
9. Push the branch
10. Open a PR with `Closes #<issue>`

This is not bureaucracy. It protects review quality.

**Assignment** prevents two people silently choosing the same work.

**Project status movement** turns the board into a coordination tool rather than
a decorative backlog.

**One issue = one branch = one PR** is the key review boundary. Once that rule
is broken, unrelated changes start hitchhiking in the same PR.

---

## 12. What we implemented this session and why

The first tickets completed in this session were:
- `#1` AI provider contract alignment
- `#5` initial auth/core Alembic migration
- `#6` hardened registration flow
- `#7` hardened login flow with cookie-backed refresh
- `#8` refresh token persistence and rotation

These were chosen in this order because they form the auth foundation.

### 12.1 Issue #1 — Align AI provider contract and schema contract

This was intentionally a small, foundational ticket.

What changed:
- tightened typing in `backend/app/ai/schemas.py`
- added a contract-oriented unit test for the provider protocol

Why start here?

Because the AI provider interface is a coordination boundary. Multiple future
tickets depend on those types and method names staying coherent. If the
contract drifts early, every later AI feature becomes more expensive to build.

This was the right first ticket because it was:
- low risk
- foundational
- narrow in scope

### 12.2 Issue #5 — Add the initial users migration

The code already had a `User` model, but without migration history the schema
was not durable. ORM definitions without migrations are just intent, not an
operational database design.

What changed:
- first Alembic revision created the `users` table
- created the `usertier` enum
- established UUID PKs and email uniqueness/indexing

Why keep the first migration small?

Because the first revision defines the base of the migration chain. A noisy
first migration is painful to reason about later. Starting with `users` only
made the base easy to understand and safe to extend.

### 12.3 Issue #6 — Harden registration flow

This was the first real auth behavior ticket.

What changed:
- stronger password validation in the request schema
- bcrypt cost explicitly pinned to 12
- `Profile` is auto-created on successful registration
- register response narrowed to only `id` and `email`
- integration tests added for success, duplicate email, and weak password

Why this mattered:

Registration is the auth root. If account creation is loose or inconsistent,
everything layered on top of it inherits that instability.

Why auto-create `Profile`?

Because the profile is not optional in the application model. It may be empty,
but it should exist. Creating it at registration time lets downstream services
assume the user already has a root profile object. That removes `None`-handling
complexity from the rest of the system.

Why narrow the response?

Public API contracts should be as small as possible. If the frontend only needs
`id` and `email`, returning `is_active`, `tier`, or other extra fields just
expands the surface area you are forced to support forever.

### 12.4 Issue #7 — Harden login flow with cookie-backed refresh

The next step was to clean up the login contract.

What changed:
- login returns only the access token in the response body
- refresh token is now set as an `HttpOnly` cookie
- failed login attempts write audit log entries
- wrong email and wrong password return the same `401`
- frontend auth flow was updated to store only the access token client-side
- refresh moved to cookie-backed usage so the frontend flow remained coherent

Why move refresh tokens into cookies?

Because refresh tokens are long-lived credentials. Storing them in JavaScript-
accessible storage (`localStorage`) increases exposure. An `HttpOnly` cookie is
not a complete security solution on its own, but it is materially better than
placing the refresh token in application-visible state.

Why change frontend code in the same ticket?

Because backend contract changes that are not reflected in the client are not
real changes; they are breakages waiting to happen. When login stopped
returning `refresh_token` in the body, the frontend needed to stop expecting it
immediately.

### 12.5 Issue #8 — Refresh token persistence and rotation

This ticket turned the cookie-backed refresh flow into an actually defensible
session model.

What changed:
- added a persisted `RefreshToken` model
- added Alembic migration for the `refresh_tokens` table
- refresh tokens are stored as **hashes**, not plaintext
- login now stores the issued refresh token server-side
- refresh now validates the stored token record
- used tokens are marked as spent
- refresh rotates to a newly issued token and updates the cookie
- replayed tokens return `401`
- integration tests cover rotation and replay prevention

Why store the hash instead of the raw token?

For the same reason passwords are hashed: if the database is exposed, plaintext
long-lived credentials should not be sitting there ready to use. Hashing a
refresh token means the DB can validate it without retaining the credential in
reusable form.

Why track `used_at`?

Because rotation is really a replay-defense mechanism. The old token should not
just become "stale"; it should become explicitly invalid because it has been
consumed. `used_at` records that state transition and makes replay detection
deterministic.

Why do this in the database rather than Redis immediately?

Database persistence is the simpler Phase 1 solution. It is slower than an
ideal Redis-based implementation, but much easier to reason about. The point of
Phase 1 is to establish correct behavior first. Performance optimization can
come after correctness.

### 12.6 Why we stopped and recovered when the branch context became ambiguous

At one point, `#8` work appeared on an unexpected branch (`fix-c3-idor-auth-me`)
instead of the intended issue branch. This was not catastrophic, but it was a
real process risk.

Why stop instead of just continuing?

Because branch identity is part of the review boundary. If the current branch is
not the branch you think it is, you can no longer trust the diff to represent
only the ticket you are working on.

The recovery process was:
1. Identify the exact `#8` files
2. Stash only those files
3. Update `main` to the newest merged state
4. Recreate `issue-8-refresh-token-rotation` from current `main`
5. Reapply only the `#8` work there

This is the right recovery method because it preserves the ticket-scoped diff
instead of dragging unknown branch context into the PR.

### 12.7 Why verification notes were explicit about missing tooling

In this shell, `pytest` was not available. Rather than pretending the tests had
run, each PR explicitly stated:
- what syntax or static checks did run
- what full test command did **not** run
- why it did not run

This is senior-engineering behavior. Honest verification notes are more useful
than vague claims of "tested." A reviewer needs to know exactly what confidence
they are getting from a PR.

### 12.8 Why `notes.md` became a key handoff document

By this point, the project has crossed from "scaffold" into "actively evolving
system." That is exactly when architecture starts becoming tribal knowledge.

`notes.md` now serves three purposes:
- architectural memory
- workflow memory
- handoff memory

That is important because future sessions or contributors should not have to
reconstruct the rationale behind:
- the issue workflow
- the auth design
- the migration chain
- the frontend/backend contract decisions

If the code shows **what** changed, this document should explain **why**.

### 12.9 Practical rule for the next tickets

The next auth tickets should follow the same discipline:

1. Ensure the previous dependent PR is merged
2. Sync local `main`
3. Branch cleanly from `main`
4. Keep the diff scoped to one ticket
5. Push and open a PR immediately after the feature is coherent

The remaining useful lesson is simple:

```
When process boundaries stay clean,
code review stays useful.
When code review stays useful,
the system stays coherent.
```

### 12.10 Issue #12 — Profile and sub-entity migrations

This ticket completed the database side of the master profile model.

What changed:
- Added migration `20260413_0003` creating `profiles`, `work_experiences`,
  `projects`, `skills`, and `certifications` tables
- `profiles.user_id` uses a `UNIQUE` FK → `users.id CASCADE` to enforce the
  1:1 user–profile relationship at the database level
- All sub-entity tables use FK → `profiles.id ON DELETE CASCADE` so deleting a
  profile atomically removes all child rows
- `source_file_id` on `work_experiences` and `projects` uses `SET NULL` (not
  `CASCADE`) because a deleted uploaded file does not mean the work experience
  should disappear — only the source link
- `bullets` is stored as `JSONB` (ordered list of strings with potential future
  structure); `skill_tags`, `tool_tags`, `domain_tags` are `ARRAY(String)`
  (flat unordered sets of text labels — no need for JSONB overhead)
- Unit tests cover the revision chain, 1:1 uniqueness constraint, and all four
  sub-entity FK relationships using the shared SQLite fixture
- JSONB/ARRAY column behavior is tested only in CI (PostgreSQL) per ADR-014

Why `UNIQUE` on `profiles.user_id` instead of a separate one-to-one table?

A separate table would be correct in a relational textbook, but adds no
practical benefit here. The `UNIQUE` constraint on the FK column is the
PostgreSQL-idiomatic way to enforce a 1:1 relationship. It is simpler,
enforced at the database level, and works correctly with `ON DELETE CASCADE`.

Why `JSONB` for bullets but `ARRAY(String)` for tags?

Bullets are a list of rich strings that may gain metadata (confidence score,
source sentence) in Phase 2 — JSONB leaves room to evolve the element schema
without a migration. Tags are flat string sets with no expected sub-structure —
`ARRAY(String)` is lighter and semantically correct.

Why put revision chain tests in unit tests instead of a separate check?

Because the migration file itself is just a Python module. Importing it and
asserting `revision`, `down_revision`, and `callable(upgrade)` is a free,
zero-dependency guard that CI runs without a database. If a future migration
accidentally sets the wrong `down_revision`, this test catches it before the
chain breaks in production.

### 12.11 Branch recovery after commit landed on wrong branch

During the `#12` session, a commit was accidentally made to `issue-2-harden-mockai`
instead of `issue-12-profile-migrations`. This happened because `git checkout -b`
created the branch but a subsequent shell CWD shift caused later `git` calls to
operate on a different branch.

Recovery:
1. Note the commit hash (`585459f`)
2. Force-move `issue-12-profile-migrations` to that hash (`git branch -f`)
3. Force-reset `issue-2-harden-mockai` back to its original tip (`git branch -f`)
4. Push `issue-12-profile-migrations` to origin

Why not cherry-pick?

Cherry-pick would have created a duplicate commit object. Since `585459f` had
the correct parent (`752a082` = current `main`), moving the branch pointer
directly was cleaner — one commit, one branch, no duplicate history.

### 12.12 Issue #25 — Deterministic scoring service and evidence mapping

This ticket turned ADR-008 from an architectural statement into executable
behavior.

Before `#25`, `scoring_service.py` was a skeleton. The weights were documented,
the intent was documented, but the implementation still returned a zero score
and persisted no useful evidence. That is an important distinction: a design is
not real until the code path exists and the behavior is testable.

What changed:
- Implemented deterministic requirement extraction inside `ScoringService` from
  structured JSON already present on the job payload
- Implemented category-specific matching across profile entities:
  - `skill` requirements match `Profile.skills[].name`
  - `tool` requirements match `WorkExperience.tool_tags` and `Project.tool_tags`
  - `experience` requirements match `WorkExperience.skill_tags` and
    `description_raw`
  - `project` requirements match `Project.skill_tags`, `description_raw`, and
    `bullets`
  - `education` requirements match `Certification.name` and `issuer`
- Added normalization and deterministic heuristics:
  - exact normalized match → `full`
  - substring/token overlap from one entity → `partial`
  - no match → `missing`
  - corroboration from multiple entities upgrades the match to `full`
- Persisted `MatchedRequirement` rows for non-missing matches, including
  `source_entity_type`, `source_entity_id`, and confidence
- Persisted `MissingRequirement` rows when no evidence exists
- Populated `ScoreBreakdown.evidence_map` so the outward-facing score payload
  points back to the same concrete profile entities as the database rows
- Added unit coverage for full, partial, and missing behavior plus stored
  evidence linkage to the correct entity ID

Why keep scoring deterministic instead of "smarter" with an LLM?

Because score generation is infrastructure, not presentation.

If an LLM decides the score, then:
- the result is not reproducible
- the reviewer cannot audit why the score changed
- the test suite can only weakly assert behavior
- the system pays token cost every time it needs a number

If deterministic code decides the score, then:
- identical inputs always produce identical outputs
- regressions are visible in ordinary unit tests
- evidence can be stored structurally, not inferred after the fact
- the LLM can be reserved for explanation instead of judgment

That split is the right architecture. The formula decides. The model explains.

Why store evidence in both `MatchedRequirement` rows and `ScoreBreakdown`?

Because they solve different problems.

The relational rows are for persistence, auditability, and later joins. They
answer questions like:
- Which profile entity satisfied this requirement?
- Was the match full or partial?
- What was the stored confidence at analysis time?

The `evidence_map` is for transport and immediate application use. It lets the
API or the next service layer read the score result without needing another
query to reconstruct the same links.

Duplicating the linkage across the database row and the returned breakdown is
intentional here. One serves storage. One serves consumption.

Why are the matching heuristics intentionally simple?

Because this phase needs explainability more than recall.

A heuristic like:
- lowercase
- strip punctuation
- compare exact strings
- fall back to substring/token overlap

is not semantically perfect, but it is debuggable. When a requirement fails to
match, a developer can inspect the input and understand why. That is much more
valuable at this stage than chasing "smarter" fuzzy matching that nobody can
reason about during code review.

This also sets the correct bar for future iteration: if synonym expansion or a
more sophisticated rules engine is added later, it should be introduced as a
deliberate change to a known baseline, not as hidden complexity in the first
version.

Real issues encountered during implementation:

1. The repository state in `/home/vic/careercore` was dirty, and `git pull
   origin main` could not fast-forward because local edits to `DECISIONS.md`
   and `notes.md` would have been overwritten.
2. The clean implementation work therefore happened in a separate worktree
   based on `origin/main`, which was the correct move. Preserving unrelated
   local work is more important than forcing the workflow through a dirty tree.
3. The shared backend test bootstrap on `main` still has environment coupling:
   `app.db.session` reads settings at import time, and its engine configuration
   is not SQLite-safe for unit tests. That means the app-level `conftest.py`
   path is not yet a clean unit-test harness for pure business logic.
4. Because of that coupling, the scoring tests for `#25` were kept as focused
   unit tests around the service behavior itself. That is not a compromise in
   rigor; it is the correct test boundary for deterministic logic while the
   broader bootstrap remains unstable.

That last point matters. Senior engineering is not "use the heaviest possible
test every time." It is choosing the narrowest test boundary that proves the
behavior you own, while being explicit about the unrelated infrastructure that
still needs cleanup.

The main lesson from `#25` is this:

```
An architecture decision is only real
when the code path, the stored data,
and the tests all agree on the same rule.
```

### 12.13 Issue #23 — Harden `POST /jobs` storage contract and ownership behavior

This ticket was narrower than the issue title initially suggests.

The existing jobs implementation on `main` already had the important ownership
shape in place:
- auth was already required on the jobs endpoints via `get_current_user`
- `JobService.list_for_user()` already filtered by `user_id`
- `JobService.get_for_user()` already used the correct double-filter
  `(JobDescription.id == job_id, JobDescription.user_id == user_id)`
- `create()` already flushed the new `JobDescription`, so generated IDs and
  stored fields were available in the response

What was not yet hardened was the input contract and the verification around
that behavior.

What changed:
- `JobDescriptionCreate` now validates `title` and `raw_text` as non-blank
  fields, not merely present fields
- `title` and `raw_text` are trimmed before persistence so the stored value
  matches the returned API value
- `company` is trimmed and normalized to `None` when the client sends only
  whitespace
- Added integration coverage for:
  - authenticated create returning a generated job ID and persisted normalized
    fields
  - unauthenticated create/list/detail requests being rejected
  - authenticated list/detail only exposing the current user's jobs

Why implement the contract in the Pydantic schema instead of the endpoint or
service?

Because this is request-shape normalization, not business logic.

The endpoint should not contain ad hoc `.strip()` calls. The service should not
have to defend itself against transport-layer whitespace quirks. The schema is
the correct place to say:
- these fields are required
- blank strings are invalid
- whitespace-only optional strings collapse to `None`

That keeps the behavior consistent no matter which caller reaches the endpoint
and makes the contract obvious in one place.

Why was there no new ADR for this ticket?

Because this issue did not add a new cross-cutting architectural rule.

The important durable rules were already captured elsewhere:
- ADR-013 already defines ownership enforcement through service-layer
  double-filters
- ADR-014 already defines the intended unit/integration test split

Issue `#23` mostly turned those existing expectations into explicit coverage for
the jobs endpoints and tightened one request schema.

Important tradeoff:

Whitespace normalization is intentionally conservative. The implementation trims
the outer boundary of `title`, `company`, and `raw_text`, but it does not
rewrite internal spacing or attempt content cleanup beyond that. That is the
right scope for an HTTP input contract. More aggressive text cleanup would risk
changing user-provided job descriptions in ways the API cannot easily justify.

Real issues encountered during implementation and testing:

1. The local repository had unrelated uncommitted changes, so they had to be
   stashed before `git pull origin main` and branch creation could proceed
   cleanly.
2. The direct local pytest path for the new integration test was blocked by an
   existing bootstrap problem: `app.db.session` creates the engine at import
   time with Postgres-style pool arguments, which is not compatible with the
   SQLite test URL used in `tests/conftest.py`.
3. The containerized verification path was also blocked by existing repository
   infrastructure: the backend Docker image currently fails during `pip install
   -e ".[dev]"` because `setuptools.backends.legacy` is unavailable in the
   build environment.

Future contributors should understand the implication of those failures:

The jobs tests added in this ticket are the correct test shape for the behavior,
but the repository's current test/bootstrap layer still needs cleanup before
they can serve as a reliable local verification path. Do not "fix" the jobs
contract to work around those unrelated issues. Fix the shared test harness or
Docker build separately, in a separate issue, and keep this ticket's scope
focused on the jobs API contract itself.

### 12.14 Issue #16 — Profile completeness calculation

This ticket replaced the placeholder completeness behavior with a real,
deterministic Phase 1 score and made sure that stored value stays current after
profile mutations.

What changed:
- `ProfileService.recalculate_completeness()` now computes a weighted score
  instead of returning a placeholder `0.0`
- the Phase 1 weights are `display_name` 10%, `current_title` 10%,
  `target_domain` 10%, at least one work experience 25%, at least one skill
  20%, at least one project 15%, and at least one certification 10%
- whitespace-only root profile fields do not count as populated
- `get_or_create()` persists `0.0` for an empty profile immediately instead of
  leaving the field as an implicit placeholder
- `update()` now recomputes and persists completeness after root profile edits
- work experience, skill, project, and certification create/update/delete
  endpoints now recompute completeness before the request transaction commits
- focused unit tests were added for empty, full, mixed, and mutation-driven
  completeness cases

Why implement it in `ProfileService` instead of scattering logic across
endpoints?

Because the scoring rule is a business rule, not an HTTP concern. The service
owns the formula and the persistence behavior. Endpoints only trigger the
service after they mutate the profile graph. That keeps the scoring contract in
one place and prevents drift where one endpoint updates the score and another
forgets.

Why a deterministic weighted score instead of AI or a more granular rubric?

Because this value is supposed to be stable and explainable. Phase 1 only needs
to answer "how much of the core profile graph exists?" not "how strong is the
profile?" A simple weighted model gives the product a predictable percentage and
avoids inventing quality judgments that are not backed by the current schema.

Important tradeoff:

The implementation checks section presence as a binary condition ("at least one
row exists") rather than trying to grade the quality of each row. That means
one project and five projects both satisfy the project portion equally. That is
intentional for Phase 1. If future contributors want richer completeness, they
must treat it as a scoring-contract change, not a small refactor.

Real issues encountered during implementation and testing:
- The accepted rule in ADR-014 says SQLite unit tests are fine for pure logic,
  but `work_experiences` and `projects` use PostgreSQL-only `JSONB`/`ARRAY`
  columns from issue `#12`. That made shared SQLite model setup unsuitable for
  this ticket's test coverage.
- The shared test environment in this shell also exposed unrelated packaging and
  ORM setup problems before the new completeness assertions could even run.
- The result was a deliberately narrow unit test around the deterministic helper
  that verifies the formula itself without pretending SQLite can exercise the
  PostgreSQL-backed profile graph.

What future contributors should understand before changing it:

`completeness_pct` is now a persisted contract, not a cosmetic placeholder. If
you add a new profile section, change the weights, or move recalculation out of
mutation paths, you are changing user-visible behavior and should update both
the ADR and the tests in the same PR.

### 12.15 Issue #10 — Enforce auth on non-public routes and document public exceptions

This issue was partly an implementation fix and partly a boundary audit.

The route tree was already close to correct. Most non-public endpoints already
declared `get_current_user`, so the main risk was not a missing dependency on
one obvious route. The real risk was relying on implicit behavior and on
FastAPI defaults that did not match the contract we wanted to preserve.

What changed:
- `get_current_user` now uses `HTTPBearer(auto_error=False)` and converts the
  missing-credentials path into the same `401 Unauthorized` response used for
  invalid and expired access tokens
- `create_app()` now exposes `/docs`, `/redoc`, and `/openapi.json` only when
  `APP_ENV` is not production
- added auth-audit tests covering:
  - missing-token `401` behavior on protected routes
  - expired-token `401` behavior
  - the route-tree rule that every non-public endpoint declares
    `get_current_user`
  - the development-vs-production docs route policy
- documented the explicit public exception set in `README.md`

Why change `HTTPBearer` instead of accepting FastAPI's default `403`?

Because `403` is the wrong semantic response for "no credentials" or "expired
credentials."

The correct contract here is:
- no token → `401`
- malformed or expired token → `401`
- authenticated user lacks permission → `403`

That distinction matters for clients, for security review, and for keeping the
code aligned with RFC 6750. If the app returns `403` before authentication has
even succeeded, the boundary becomes harder to reason about.

Why disable docs and OpenAPI in production?

Because they are a public exception, not part of the authenticated product
surface.

The issue did not require hiding `/health`; that endpoint remains public by
design for deployment probes. But interactive docs and schema discovery are a
different category. They are useful in local development and review
environments, but they should not stay exposed in production by accident just
because FastAPI makes it easy.

Important tradeoff:

This issue uses an explicit exception list rather than trying to infer "public"
routes from tags or naming conventions. That is intentionally rigid. Security
boundaries should be obvious in code review. If a future contributor wants to
make a route public, that should be a deliberate product decision with matching
docs and tests, not an incidental refactor.

Real issues encountered during implementation and testing:
- The shared local backend environment in this workspace is still unstable for
  normal test execution. Import-time settings and database engine construction
  continue to make the lightweight local test path fragile.
- Because of that, the most reliable guardrail for the route audit was a static
  test over the endpoint source tree rather than a fully booted app import.
- That is acceptable here because the rule being enforced is structural: which
  endpoints declare `get_current_user`, and which routes are explicitly allowed
  to remain public.

What future contributors should understand before changing it:

The default rule is now "protected unless explicitly listed as public." If you
add a new route and it does not belong in the small public exception set, wire
`get_current_user` into the endpoint immediately and extend the tests in the
same PR. If you think a new route should be public, treat that as a security
policy change, not a convenience tweak.
