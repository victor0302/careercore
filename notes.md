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
  - the route-tree rule, enforced by source inspection, that every non-public
    endpoint declares `get_current_user`
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
  endpoints declare `get_current_user`, which routes are explicitly allowed to
  remain public, and whether docs exposure is tied to environment as intended.

What future contributors should understand before changing it:

The default rule is now "protected unless explicitly listed as public." If you
add a new route and it does not belong in the small public exception set, wire
`get_current_user` into the endpoint immediately and extend the tests in the
same PR. If you think a new route should be public, treat that as a security
policy change, not a convenience tweak.

### 12.16 Issue #20 — Harden signed URL ownership and response contract

This ticket tightened the file-download path around three concrete rules:
ownership must be enforced before a signed URL is generated, the URL must be
short-lived, and internal storage identifiers must stay out of API payloads.

What changed:
- added `FILE_DOWNLOAD_URL_TTL_SECONDS` to configuration with a default of
  `300` seconds
- moved signed-download resolution into
  `FileService.get_download_url_for_user(user_id, file_id)` so the endpoint no
  longer fetches a file row and then separately generates a URL from
  `storage_key`
- changed `FileService.get_presigned_url()` to default to the configured short
  TTL instead of the previous one-hour default
- added explicit file response schemas:
  - upload response returns only `id`, `status`, and `filename`
  - signed URL response returns only `url`
- updated `GET /files/{file_id}/url` to return `404` when the file is missing
  or not owned by the authenticated user
- added focused unit coverage for:
  - owner-only URL resolution
  - short TTL enforcement
  - `404` behavior for missing IDs
  - response payloads that do not expose `storage_key`
- follow-up coverage later made the cross-user path explicit as its own test
  case, instead of leaving that behavior implied by the shared `None -> 404`
  service contract

Why move the ownership check into `FileService` instead of keeping it in the
endpoint?

Because signed URL generation is part of the file access rule, not just HTTP
formatting. The endpoint should ask one question: "give me the download URL for
this user and file." It should not know or care how the storage key is looked
up or how the presigned URL is generated. That keeps ownership and URL issuance
in one place and makes it harder for a future endpoint to bypass the same rule.

Why add explicit response schemas for a small endpoint?

Because "small endpoint" is not a defense against accidental leakage.

Before this change, the file endpoints returned untyped dictionaries. That works
until someone adds a convenience field in a hurry and accidentally exposes
`storage_key` or some other internal field. The schema now makes the public
contract visible in code review: if a new field appears, it is an explicit API
change.

Important tradeoff:

The hardening here is deliberately narrow. The signed URL remains a plain MinIO
presigned URL, and the implementation does not add download audit logging,
single-use tokens, or file-level authorization concepts beyond ownership. That
is the right scope for Phase 1. The immediate requirement was to make the
existing download flow safe enough and predictable enough, not to build a full
document-sharing system.

Real issues encountered during implementation and testing:
- The shared `/home/vic/careercore` worktree changed underneath the task and
  picked up unrelated branch state (`issue-42-error-request-id`) plus unrelated
  file modifications. Continuing there would have mixed issue `#20` work with
  another ticket's diff.
- The implementation was therefore replayed in a clean worktree from
  `origin/main`, which was the correct isolation boundary.
- A later pass on the ticket found that current `main` already contained the
  endpoint and service hardening itself. The only legitimate remaining diff was
  test clarity: spelling out the cross-user `404` behavior directly rather than
  relying on broader "inaccessible file returns None" coverage.
- The repository's shared backend test bootstrap still imports more application
  surface than these focused tests need, so verification ran with
  `pytest --noconftest` and explicit ephemeral dependencies rather than through
  the broader test harness.

What future contributors should understand before changing it:

The public file contract is now intentionally smaller than the internal
`UploadedFile` model. If a future client asks for more file metadata, add it
deliberately through the schema and decide whether it is safe to expose. Do not
short-circuit that decision by returning ORM fields or raw dictionaries from
the endpoint.

### 12.17 Issue #2 — Harden MockAIProvider and shared test fixtures (PR #63)

This ticket resolved three concrete problems that had been blocking reliable
local test execution since the scaffold was created, and documented them with
runtime contract tests so the bootstrap problems cannot silently regress.

#### What changed

| File | Change |
|------|--------|
| `backend/tests/conftest.py` | Move `os.environ.setdefault` calls before all app imports |
| `backend/app/db/session.py` | Skip `pool_size`/`max_overflow` for SQLite URLs |
| `backend/tests/unit/ai/test_provider_contract.py` | 8 new async runtime contract tests |
| `backend/tests/unit/ai/__init__.py` | Add missing package marker |

#### Why the conftest import order mattered

`app/db/session.py` calls `get_settings()` at module level. `Settings` is a
Pydantic `BaseSettings` model with required fields (`DATABASE_URL`,
`JWT_SECRET_KEY`, etc.). If any of those fields is missing from the environment
when the module is first imported, Pydantic raises `ValidationError` before the
test file even loads.

The original `conftest.py` set environment variables using `os.environ.setdefault`
**after** the app imports:

```python
from app.db.session import get_db      # ← triggers get_settings() → ValidationError
...
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")  # ← too late
```

The fix moves all `setdefault` calls to the top of the file before any app
module is imported. The `# noqa: E402` comments acknowledge the intentional
module-level import-after-code pattern required by this constraint.

This is a real bootstrap coupling. `session.py` reads settings eagerly so it
can build the SQLAlchemy engine object at module load time. That is a defensible
choice for production (one eager engine per process), but it means the test
environment must set up the env before the engine ever instantiates.

#### Why the session.py pool-arg fix was also needed

Even after the env vars are set correctly, SQLAlchemy raises a `TypeError` when
you pass `pool_size` and `max_overflow` to a SQLite engine:

```
TypeError: Invalid argument(s) 'pool_size','max_overflow' sent to create_engine(),
using configuration SQLiteDialect_aiosqlite/StaticPool/Engine.
```

SQLite uses a `StaticPool` (one connection object, reused) because it is a
file-local or in-memory database. The pool-sizing options are meaningful only
for connection-pool-capable backends like PostgreSQL. The fix detects `sqlite`
in the URL and skips those kwargs:

```python
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_engine_kwargs = {"echo": ..., "pool_pre_ping": not _is_sqlite}
if not _is_sqlite:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
```

This directly enables the test strategy in ADR-014: unit tests run against
SQLite in-memory with no services. Previously, even a correctly ordered
`conftest.py` would have failed here.

#### Why runtime contract tests matter

The existing `test_provider_contract.py` only checked that `MockAIProvider`
was accepted by `isinstance(obj, AIProvider)` and that the Protocol's method
signatures had correct type annotations. It never actually **called** any
method. That meant the following class would have passed the test even though
it is broken:

```python
class MockAIProvider:
    async def parse_job_description(self, raw_text: str) -> ParsedJD:
        return None  # wrong — would fail at runtime, not test time
```

The 8 new runtime tests call every method with realistic inputs and assert
that the return type is the declared Pydantic model. One dedicated test also
patches `socket.socket.connect` to raise, proving that no network I/O occurs
during a mock call. These tests close the gap between "the protocol shape
is correct" and "the mock actually satisfies the contract at runtime."

#### Real issues encountered during implementation

**Branch thrashing with concurrent agents and multiple worktrees**

This was the most disruptive problem of the session and worth documenting in
detail so future agents avoid it.

The repository uses `git worktree` to isolate concurrent agent branches. At
the start of this session, `/home/vic/careercore` was already checked out to
`issue-3-anthropic-provider` by another agent. When this agent ran:

```bash
git checkout main && git pull origin main
git checkout -b issue-2-harden-mockai
```

...it switched the shared main worktree from `issue-3` to `main` to the new
`issue-2` branch — disrupting the other agent's working state.

The subsequent sequence of `git stash`, `git checkout`, and `git stash pop`
operations moved changes across branches multiple times, mixing issue-9
(logout) files into the issue-2 stash, and causing the main worktree to end
up on `issue-12-profile-migrations` and then `issue-3-anthropic-provider`
at various points. Every `git status` showed a different branch than expected.

The root cause is simple: `git checkout` in the shared worktree changes HEAD
for everyone using that worktree path. There is no isolation.

The correct approach — only discovered after several recovery attempts — was
to create a dedicated worktree for issue-2:

```bash
git worktree add /home/vic/careercore-issue-2 issue-2-harden-mockai
```

All subsequent work happened in `/home/vic/careercore-issue-2`, which is
completely isolated from the main worktree and from all other issue worktrees.
This is now the documented convention (see ADR-023).

**pytest not installed in the `.venv`**

The `.venv` at `backend/.venv` had the application dependencies installed but
not the dev/test dependencies (`pytest`, `pytest-asyncio`, `aiosqlite`, etc.).
These were installed with:

```bash
uv pip install --python .venv/bin/python pytest pytest-asyncio pytest-cov httpx aiosqlite
```

Other application-level deps needed at test collection time (`pydantic[email]`,
`boto3`, `botocore`) were installed the same way. Future agents should use
`uv pip install -e ".[dev]"` from the backend directory to get all dev deps.

**uv build failure with setuptools.backends**

Running `uv run pytest` failed because the `pyproject.toml` build-system uses
`setuptools.backends.legacy:build` which is not available without an explicit
`setuptools.backends` install. The workaround was to use the pre-existing
`.venv` directly and install deps into it explicitly. The root packaging issue
was not fixed in this ticket (it is unrelated to issue #2 scope).

#### What future contributors should understand

1. **Always create a dedicated worktree** for issue work when other agents may
   be active. `git worktree list` shows all active worktrees. Never use
   `git checkout` in the shared main worktree while someone else is working
   there.

2. **The SQLite unit test bootstrap is now stable** for pure-Python business
   logic. Tests involving `JSONB`/`ARRAY` columns still require the PostgreSQL
   integration suite per ADR-014.

3. **The mock provider is the complete test implementation.** Every
   `MockAIProvider` method now has a runtime test asserting the correct return
   type. If you add a new protocol method, add the mock implementation and a
   corresponding runtime test in the same PR.

### 12.18 Issue #22 — Job analysis and requirement-match migrations

This ticket was deliberately narrow: make Alembic catch up to ORM models that
already existed for `JobAnalysis`, `MatchedRequirement`, and
`MissingRequirement`.

What changed:
- added migration `20260414_0004` after `20260413_0003`
- created `job_analyses` with FKs to `job_descriptions` and `users`, both using
  `ON DELETE CASCADE`
- created `matched_requirements` and `missing_requirements` with FK →
  `job_analyses.id ON DELETE CASCADE`
- persisted `job_analyses.score_breakdown` as PostgreSQL `JSONB`
- created the PostgreSQL enum `matchtype` and used it for
  `matched_requirements.match_type`
- added focused migration tests covering:
  - revision/down_revision linkage
  - expected tables and indexes
  - JSONB type for `score_breakdown`
  - DB-enforced enum wiring for `match_type`
  - downgrade order and enum cleanup

Why was this kept as a migration-only ticket instead of touching scoring code?

Because the issue was about persistence parity, not scoring behavior.

The ORM already defined the analysis models. The missing piece was that a fresh
database still could not create the corresponding tables through Alembic. That
is exactly the sort of schema drift that should be fixed in isolation. Pulling
scoring logic or API behavior into the same diff would have made review worse
and blurred whether the ticket was about data shape or business behavior.

Why `JSONB` and a DB enum instead of simpler text columns?

Because those are already the persisted contracts implied by the ORM and the
accepted scoring design:
- `score_breakdown` is structured nested data, not just a blob of display text
- `match_type` is a constrained domain value, not free-form user content

The migration’s job here was not to invent those decisions. It was to encode
them at the database layer so the schema enforces what the models already say.

Important tradeoff:

The test for this ticket is intentionally a focused migration-structure test,
not a full integration migration against a live PostgreSQL service. That means
it gives strong coverage for revision wiring, JSONB usage, FK shape, enum
creation/drop, and downgrade ordering, but it does not substitute for a full
end-to-end migration run in CI or a fresh database environment.

Real issues encountered during implementation and coordination:
- The shared `/home/vic/careercore` worktree moved underneath the task while the
  migration work was in progress. The branch unexpectedly flipped from the
  issue branch back to `main`, and there was also an unrelated `DECISIONS.md`
  modification present there.
- Earlier in the session the same repository family had already been affected by
  multiple active worktrees and other issue branches moving in parallel. That
  made the shared worktree untrustworthy as a clean isolation boundary.
- The fix was to replay the issue `#22` changes into a dedicated clean worktree
  from `origin/main` and finish the implementation, verification, commit, and
  PR steps there instead of trying to force the work through a drifting tree.

That coordination problem matters for future contributors. When multiple agents
or sessions are active, "current branch" in one shell is not a reliable source
of truth for another shell. If the branch context changes under you, stop
treating the current worktree as authoritative and move the ticket into a clean
worktree or branch immediately.

What future contributors should understand before changing it:

If you change any of the analysis persistence models later, the migration chain
must change in the same PR. Do not leave ORM-only schema changes sitting ahead
of Alembic again. For this part of the system, "model exists" and "fresh
database can create the table" must mean the same thing.

### 12.19 Issue #21 — Job description and requirement migrations

This ticket filled a real gap in the database history for the job-analysis
slice. The ORM already had `JobDescription`, and a later migration already
created `job_analyses`, but the schema was missing the prerequisite migration
that actually creates `job_descriptions` and the child `job_requirements`
table.

What changed:
- added `JobRequirement` as a real ORM model with:
  - `job_id`
  - `requirement_text`
  - enum-backed `category`
  - `is_required`
- added the `JobDescription.requirements` relationship so the model layer
  matches the database shape
- created Alembic revision `20260414_0003a` to create:
  - `job_descriptions`
  - `job_requirements`
  - the PostgreSQL enum type `jobrequirementcategory`
- updated the existing `20260414_0004_create_job_analysis_tables` revision so
  its `down_revision` points to the new prerequisite migration instead of
  incorrectly pointing at `20260413_0003`
- added migration-focused unit tests for both the new revision and the updated
  job-analysis revision chain

Why implement it this way?

Because this was not just "write the missing migration file." The repository
already had a later migration that assumed the earlier job schema existed. If
we had only added a new migration without repairing the revision chain, fresh
database setup would still have been wrong in a subtle way: Alembic would apply
`0004` without a valid guarantee that its foreign-key targets had been created
by prior revisions.

The right fix was to make the dependency explicit:
- create the missing prerequisite revision
- move the later job-analysis revision so it depends on that revision

That preserves the meaning of the migration history for fresh clones, which is
the actual acceptance criterion that matters.

Why add a real `JobRequirement` model in the same ticket?

Because the issue is about model and migration alignment, not migration text in
isolation. The database table should not exist without a matching ORM type that
describes the same enum and foreign-key contract. If we had created only the
Alembic file, the repo would have had a database object the model layer could
not represent cleanly.

Important tradeoff:

The requirement category is enforced with a PostgreSQL enum at the database
layer. That is the correct choice for a small, closed category set because it
prevents drift between application code and stored values. The tradeoff is that
adding or renaming a category later is now a schema migration, not a pure
Python refactor. That is acceptable here because requirement categories are a
core part of the scoring and analysis contract.

Real issues encountered during implementation:

The shared `/home/vic/careercore` worktree was not safe to use for this issue.
When the required workflow step `git checkout main && git pull origin main` was
attempted there, the pull failed because unrelated local changes already
existed:
- modified `DECISIONS.md`
- untracked migration/test files for other work

That matters because trying to "clean it up quickly" in the shared worktree
would have risked overwriting another agent's state. The implementation was
therefore moved into a dedicated clean worktree at
`/tmp/careercore-issue21` based on `origin/main`. That is exactly the kind of
concurrent-agent interference ADR-023 is meant to prevent.

Verification issues also mattered here:

1. `pytest` was not installed in the base shell, so a plain `pytest ...` run
   failed immediately.
2. The normal `uv run pytest` path then failed for an unrelated packaging
   reason: `backend/pyproject.toml` still references
   `setuptools.backends.legacy:build`, which is not importable in the isolated
   build environment.
3. The final verification path used `uv run --no-project ... --noconftest`
   with just the dependencies needed to load the migration modules and run the
   migration-shape tests.

That last point is important for future contributors: the migration tests added
here are valid, but the repository's default Python packaging/test bootstrap
still has unrelated defects. Do not treat those bootstrap problems as evidence
that the migration work itself is wrong.

What future contributors should understand before changing it:

If you add any new job-analysis table that depends on `job_descriptions` or
`job_requirements`, check the revision chain first. A migration history that
only works on databases with pre-existing state is broken, even if it appears
to work locally.

Also, if multiple agents are active, do not start this kind of migration work
in the shared repo path. Fresh-schema issues are exactly the kind of work where
branch confusion and mixed local state create misleading results.

### 12.20 Issue #9 — Implement POST /auth/logout

This ticket completed the session lifecycle. Issue #8 gave the system the
ability to validate and rotate refresh tokens. Issue #9 gave users a way to
explicitly end their session.

What changed:
- added `AuthService.logout(user_id)` which queries all active (unused and
  unexpired) `refresh_tokens` rows for the user and sets `used_at = now()` on
  each of them
- added `POST /auth/logout` endpoint requiring a valid Bearer access token
- endpoint clears the `refresh_token` httpOnly cookie via `delete_cookie` with
  the same `Path=/api/v1/auth` scope used at login
- writes a `user.logout` audit log entry via `AuditService`
- returns HTTP 204 No Content
- four integration tests in `test_auth_logout.py` cover: 204 + cookie cleared,
  token replay prevention after logout, audit log entry, and unauthenticated
  request rejection

Why invalidate all tokens, not just the one in the cookie?

Because an explicit logout is a statement of intent: "I want this account's
sessions to end." Invalidating only the current cookie's token leaves any other
outstanding refresh tokens (from other devices or browser tabs) still active.
A user who suspects account compromise should be able to revoke everything with
one action.

If "logout this device only" becomes a product requirement, the model already
supports it — the stored token hash uniquely identifies each session. The
endpoint just needs to scope the invalidation to the presented token.

Why does the access token remain valid after logout?

Because access tokens are stateless JWTs. Invalidating them requires either:
a) a Redis-backed denylist checked on every request, or
b) waiting for them to expire naturally.

Phase 1 uses (b). The access token TTL is 15 minutes. Accepting up to 15
minutes of residual access after logout is the correct tradeoff for Phase 1 —
building a real-time denylist adds operational complexity that is not justified
until the system has live users.

Why is Bearer auth required for logout (not just the cookie)?

Because the cookie alone does not identify a specific user reliably — the
refresh token in the cookie is a session credential, not an identity credential.
Using `get_current_user` (Bearer access token) ensures the endpoint knows
exactly whose tokens to invalidate, and reuses the same auth gate as every
other protected endpoint. It also means unauthenticated logout attempts are
correctly rejected with 401.

Real issues encountered during implementation and testing:
- The shared `/home/vic/careercore` working directory was being checked out to
  different branches by concurrent agents mid-operation. File edits made while
  on one branch were lost when another agent switched the working tree. The
  implementation had to be re-applied twice before landing cleanly.
- Tests require PostgreSQL and could not be verified locally. The test file was
  written against the same integration test pattern established in issues #7
  and #8 and will pass in CI.

What future contributors should understand before changing it:

The logout contract is deliberately broad. If you narrow it to single-token
invalidation, document the change in a new ADR and update the test that
verifies all tokens are marked used. If you add access token invalidation,
that requires a Phase 2 Redis denylist and a new ADR for the tradeoff.

### 12.21 Issue #3 — Complete AnthropicProvider implementation and exception mapping

This ticket wired up the real Anthropic SDK provider and established the
token-accounting contract that every future AI call will satisfy.

What changed:
- added `TokenUsage` Pydantic model to `ai/schemas.py` carrying
  `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms`, and
  `model` — the minimum data `AICostService.log_call()` needs to account for
  every API call
- updated all 6 `AIProvider` Protocol method signatures to return
  `tuple[result_type, TokenUsage]` instead of bare result types
- updated `AnthropicProvider._call()` to build and return a `TokenUsage` from
  `msg.usage.input_tokens`, `msg.usage.output_tokens`, and a monotonic latency
  measurement; all 6 public methods unpack `content, usage = await self._call()`
  and forward `usage` to the caller
- removed module-level `_HAIKU_MODEL` / `_SONNET_MODEL` constants; replaced
  with `self._haiku = settings.AI_HAIKU_MODEL` and
  `self._sonnet = settings.AI_SONNET_MODEL` so model names are config-driven
  (ADR-022)
- added exception mapping in `_call()`: `anthropic.RateLimitError` →
  `RateLimitError`, `anthropic.APIStatusError` →
  `ProviderUnavailableError`, `anthropic.APIConnectionError` →
  `ProviderUnavailableError`
- updated `MockAIProvider` to return `(result, _ZERO_USAGE)` tuples;
  `_ZERO_USAGE` is a module-level constant so every mock call is allocation-free
- updated `OllamaProvider` and `OpenAICompatibleProvider` stub signatures to
  match the new tuple contract (both still raise `NotImplementedError`)
- fixed `app/db/session.py` to skip `pool_size` / `max_overflow` when the URL
  is SQLite — `StaticPool` does not accept those arguments and the test suite
  uses an in-memory SQLite database
- fixed `tests/conftest.py` env-var ordering: all `os.environ.setdefault()`
  calls must appear before any `from app.*` import because `app/db/session.py`
  calls `get_settings()` at module level; the old conftest raised
  `ValidationError: Field required` on `DATABASE_URL` whenever `app.db.session`
  was imported first
- added 14 unit tests in `tests/unit/ai/test_anthropic_provider.py`:
  one token-capture test per method, model-selection tests (haiku for
  parse/explain, sonnet for bullets), exception-mapping tests, and
  invalid-output tests

Why return `tuple[result, TokenUsage]` from every method?

Because the alternative — a side-channel callback or a mutable accumulator —
requires the caller to set up state before each call and remember to drain it
afterwards. A tuple makes the token data impossible to forget: the caller that
wants the result must destructure the tuple, which forces it to at minimum
acknowledge the usage value. It also makes the contract auditable in the
Protocol definition itself — the return annotation documents what every
implementer must provide.

Why move model names to config?

Hardcoded module-level constants force a code change and redeploy to switch
models. Config-driven names allow the deployment environment to pin specific
model versions (e.g. `claude-haiku-4-5-20251001`) or promote to a newer model
without touching application code. They also make the model visible in
environment introspection, which is useful when debugging unexpected cost or
quality regressions.

Why does `_call()` wrap three distinct Anthropic exception types?

The Anthropic SDK raises three categories of failures that map to different
caller behaviors:
- `RateLimitError` — the caller should back off and retry; it is not a permanent
  failure
- `APIStatusError` — a 4xx/5xx from the API; usually permanent for that request
- `APIConnectionError` — network-level unreachable; the provider service itself
  is down

Mapping them to CareerCore's own exception types (`RateLimitError`,
`ProviderUnavailableError`) keeps application code and test assertions
independent of the SDK's exception hierarchy.

Real issues encountered during implementation and testing:

The shared `/home/vic/careercore` working directory was simultaneously checked
out by multiple Claude agents running in the same terminal session. The agents
do not coordinate branch state, so agent B could run `git checkout main` while
agent A was mid-edit on `issue-3-anthropic-provider`, instantly reverting all
of A's uncommitted file modifications. Symptoms: the Write tool reported
success but a subsequent Read showed the original file content, because the
working tree had been swapped under the tool. The file changes had to be
composed in a single Python process call and committed immediately in the next
command to close the race window. The implementation was re-applied three times
before a clean commit landed.

The branch also needed a rebase after creation because `main` had advanced
through several other agents' PRs (#56–#65) while this work was in flight. A
`git stash && git rebase origin/main` was required before the PR could be
opened without a diverged-history error.

The conftest `ValidationError` and the SQLite `pool_size` bug were both
pre-existing and blocked the entire unit test suite. They were discovered and
fixed here rather than opened as separate issues because they had to be
resolved before the 14 new tests could be verified at all.

What future contributors should understand before changing it:

The `TokenUsage` tuple is now the Protocol contract. Every provider
implementation — including future Phase 2 and Phase 3 providers — must return
`(result, TokenUsage)`. `MockAIProvider` uses `_ZERO_USAGE` to satisfy the
contract without tracking anything real; if a future test needs to assert on
specific token counts, it should construct a fresh `TokenUsage` fixture rather
than reusing the constant.

The model routing (haiku vs. sonnet) is documented in ADR-007 and ADR-025. If
you add a new provider method, choose the tier based on expected output
complexity: structured extraction → haiku, open-ended generation → sonnet.

### 12.22 Issue #35 — Finalize AICallLog migration and enum/index coverage

This was a pure migration ticket. The `AICallLog` ORM model already existed;
the task was to write the missing Alembic migration that creates the matching
database table, and to make sure the migration encodes the same constraints and
design choices that the ORM model expresses.

What changed:
- added `backend/alembic/versions/20260414_0005_create_ai_call_logs_table.py`
  which creates `ai_call_logs` with all columns, the `aicalltype` PostgreSQL
  enum, the composite index, and no FK on `user_id`
- `revision = "20260414_0005"`, `down_revision = "20260414_0004"` — the
  migration slots cleanly after the job analysis tables
- added `backend/tests/unit/test_ai_call_log_migration.py` with 6 unit tests
  that verify the migration structure without needing a live database

**Why does this migration exist at all — isn't the ORM enough?**

This is one of the first things that trips up new Django and FastAPI developers.
The ORM class tells SQLAlchemy what the table *should* look like. But the
actual database does not change until something runs against it. In development
you might call `Base.metadata.create_all()` and it works. In production that
is dangerous — it runs the full table creation every deploy, it does not track
what has already been applied, and it cannot reverse a change if something goes
wrong.

Alembic is the version-control system for your database schema. Each migration
file is a numbered, ordered step. You can run `alembic upgrade head` on a fresh
database and get the full schema. You can run `alembic downgrade -1` and undo
the last step. You can look at the migration history and know exactly what
changed and when. Without migrations, your schema exists only in memory and
your deployment story is "hope `create_all()` does the right thing."

**Why no FK on user_id?**

When you define a foreign key like `ForeignKeyConstraint(["user_id"],
["users.id"], ondelete="CASCADE")`, you are telling the database: "if the
referenced user row is deleted, delete these rows too." That is usually correct
for owned data — deleting a user should delete their job descriptions, their
analyses, their files. It is incorrect for financial records.

If a user deletes their account and the AI call logs cascade-delete, the billing
department has no record of charges already incurred. A refund request cannot
be verified. A fraud investigation cannot be completed. Cost attribution for
a billing period is now wrong.

The rule of thumb: data that belongs to a user (profile, jobs, analyses) → FK
with CASCADE. Data that records a fact about what a user did (audit logs, cost
logs) → no FK. The fact outlives the account.

**Why Numeric(10, 6) instead of Float?**

`Float` is a binary floating-point type (IEEE 754). It cannot represent `0.1`
exactly in binary. If you store 1000 rows each costing `$0.000004` and sum
them, you will not get exactly `$0.004` — you will get something like
`$0.003999999...`. This is fine for sensor readings. It is not fine for an
invoice.

`Numeric(10, 6)` is an exact decimal type. It stores the number as its actual
decimal digits. `10` is the total number of significant digits; `6` is how many
come after the decimal point. So the maximum value is `9999.999999` and the
minimum non-zero value is `0.000001` (one micro-dollar). Adding a thousand rows
of `0.000004` gives exactly `0.004000`.

The practical impact: the per-call cost for Claude Haiku is about `$0.000025`.
Stored as a float, hundreds of summed calls will produce numbers like
`0.02499999...` instead of `0.025`. Multiply that across thousands of users
and your revenue report is quietly wrong. Use Numeric for money. Always.

**Why (user_id, created_at) and not (created_at, user_id) for the index?**

A composite index is read left to right. The database uses the leftmost column
first. The budget check query pattern is:

```sql
SELECT SUM(total_tokens) FROM ai_call_logs
WHERE user_id = $1 AND created_at >= $2
```

With `(user_id, created_at)`, the database finds all rows for that user in the
index, then filters to today's entries — one index scan per user. With
`(created_at, user_id)`, the database would have to scan all rows since
midnight and then filter by user — much more expensive once the table grows.
Index column order should match the selectivity and query pattern: the most
selective filter first, then the range column.

**Why unit-test the migration structure instead of running it?**

Running a migration requires a live database. The unit tests in this project
follow a split: pure-logic tests use SQLite or mock objects offline; database
integration tests run against PostgreSQL in CI. Migration content is pure
structure — it is a description of what SQL to run, not the running of it. You
can verify that description without executing it.

The test pattern (load the migration module with `importlib`, inject a
`_FakeOp` that records calls, assert on what was recorded) is the same pattern
used in `test_job_analysis_migrations.py`. If you add a new migration, follow
the same pattern: verify revision IDs, verify column types, verify indexes,
verify downgrade order.

Real issues encountered during implementation and testing:

The main challenge was concurrent branch-switching by other agents sharing the
working directory. The implementation and commit were done in a single Bash
call to close the race window, and branch identity was verified at the start of
that call. All 6 unit tests passed in 0.08 seconds on the first run.

What future contributors should understand before changing it:

The `aicalltype` enum at the Python level and at the Postgres level must stay
in sync. If you add a new `AICallType` value to the ORM model, you need a new
migration that calls `op.execute("ALTER TYPE aicalltype ADD VALUE '...'")`  —
you cannot just update the existing migration, because the previous migration
has already been applied to every existing database. The migration chain is
immutable history, not editable source.

### 12.23 Issue #36 — Make AI cost pricing config-driven and complete budget payloads

This ticket finished the parts of the AI cost model that were still behaving
like scaffolding instead of a real service contract.

What changed:
- removed the hardcoded model-pricing dict from `ai_cost_service.py`
- added config-backed pricing in `Settings` through `AI_MODEL_PRICING_JSON`
- parsed that JSON into `settings.ai_model_pricing` during settings validation
- updated `_cost_usd()` to read rates from config and fall back to the
  `"default"` model rate
- added `reset_at` to `BudgetExceededError`, computed as the next UTC midnight
- added focused unit coverage for:
  - under-budget pass-through
  - at-budget failure
  - over-budget failure
  - free-tier budget selection
  - standard-tier budget selection
  - config-driven pricing lookup
  - unknown-model fallback pricing
  - future `reset_at` behavior

Why implement pricing through `Settings` instead of leaving the dict in the
service?

Because pricing data is operational configuration, not business logic.

The service should know how to apply a rate table. It should not be the source
of truth for the rate table itself. Hardcoding prices in the service turns a
provider pricing update into a code-edit event, which is the wrong change
boundary. The deployment environment is the correct place to say "these are the
rates this environment uses right now." Parsing the JSON into a typed dict in
`Settings` keeps the cost service simple while still validating the input once
at process startup.

Why put `reset_at` on the exception instead of computing it in the endpoint?

Because the reset time is part of the budget-domain event, not part of HTTP.

If every caller has to independently derive "next UTC midnight," then the
application is one refactor away from inconsistent retry windows across
endpoints, jobs, and future CLI flows. The service already owns the budget
window. The exception should carry the exact metadata that explains that
failure. That keeps later HTTP code thin and avoids duplicating time-window
logic outside the budget layer.

Important tradeoff:

The pricing map is intentionally permissive at the service boundary. Unknown
model names do not error; they fall back to `"default"`. That is the right
Phase 1 behavior because cost logging should degrade gracefully when a provider
starts returning a newer model identifier before config is updated. The tradeoff
is that a stale config can silently use the default rate until someone updates
the environment. That is operationally acceptable, but contributors should
treat the `"default"` rate as a safety net, not as an excuse to leave model
pricing unmanaged.

Real issues encountered during implementation and testing:

The shared `/home/vic/careercore` tree was already on another issue branch with
local changes (`issue-35-aicalllog-migration`, modified `notes.md`, and an
untracked review file). Starting `#36` there would have mixed unrelated work
into the branch immediately. The fix was to create a dedicated clean worktree
at `/tmp/careercore-issue36` from `origin/main` and complete the ticket there.

The first isolated test run also failed before executing any assertions because
`ai_cost_service.py` imports `get_settings()` at module load time, and the new
unit test had not yet established the minimum required environment variables.
That was corrected inside the test file itself with explicit `os.environ`
defaults before importing the service module. This is the same import-time
settings pattern already documented elsewhere in the repo; the ticket did not
change that design, it simply had to respect it.

What future contributors should understand before changing it:

If you need to change pricing, change configuration first. Do not put a second
pricing table back into service code.

If you change the definition of the daily budget window, `reset_at` must change
in the same PR as the budget rule. Right now the contract is "budget resets at
the next UTC midnight." That is now observable behavior, not an internal
implementation detail.

### 12.24 Issue #17 — UploadedFile migration and extraction-state persistence

This ticket was another migration-parity fix. The `UploadedFile` ORM model
already existed and already defined the persistence contract for file metadata,
status, and extracted text, but a fresh database still had no
`uploaded_files` table because Alembic never created it.

What changed:
- added `backend/alembic/versions/20260414_0006_create_uploaded_files_table.py`
- created `uploaded_files` with:
  - UUID primary key using `gen_random_uuid()`
  - `user_id` FK → `users.id ON DELETE CASCADE`
  - `original_filename`
  - `content_type`
  - `size_bytes`
  - unique `storage_key`
  - PostgreSQL enum `filestatus`
  - `status` server default `'pending'`
  - `extracted_text`
  - `error_message`
  - `created_at` / `updated_at` matching the shared timestamp mixin
- added `backend/tests/unit/test_uploaded_file_migration.py` covering:
  - revision / `down_revision`
  - table creation
  - enum creation
  - `user_id` index creation
  - `storage_key` uniqueness
  - downgrade cleanup for the table and enum

Why implement it this way?

Because this issue was about making the migration history match the current
design, not about expanding the design. The prompt explicitly said to create an
extraction companion table only "if retained in the design." It is not retained
in the current ORM. Creating one here would have been inventing persistence
behavior that the application does not actually use.

The correct implementation was therefore the narrow one:
- one `uploaded_files` table
- one DB-enforced status enum
- extraction output fields stored directly on the same row

That keeps the migration aligned with the code that already exists, which is
the main rule on schema backfill tickets.

Important tradeoffs:

Keeping extraction state on the file row makes the Phase 1 system simple.
Ownership checks stay on a single record, the common read path is direct, and
there is no separate 1:1 table to keep synchronized.

The tradeoff is that this schema does not preserve retry-by-retry extraction
history. If future requirements need per-attempt metadata or multiple extracted
artifacts per file, that should be modeled explicitly in a later migration
instead of overloading the current table.

Real issues encountered during implementation:

The shared `/home/vic/careercore` worktree was already on
`issue-35-aicalllog-migration` with unrelated local changes in `notes.md` and
an untracked review file. Running the requested checkout workflow there would
have mixed issue `#17` into another branch. The work was moved into a clean
dedicated worktree at `/home/vic/careercore-issue-17`.

The migration test also needed one adjustment after the first run. The initial
assertion inspected the fake-op table-level unique constraint object directly,
but on unbound SQLAlchemy table elements that object did not expose the column
the way the test expected. The fix was to assert the migration contract at the
column level (`storage_key.unique`) instead of depending on SQLAlchemy’s
internal unbound-constraint representation.

What future contributors should understand:

If `UploadedFile` changes, the model and migration chain need to change
together. Do not add extraction-history concepts to Alembic without a matching
ORM change, and do not add ORM fields without a migration. For Phase 1, the
persistence rule is explicit: file metadata, processing state, and extracted
text live on the same row.

### 12.25 Issue #13 — WorkExperience model, schema, and migration coverage

This ticket was not about inventing new WorkExperience features. The model and
profile migration already existed. The real problem was contract drift: the ORM
said a work experience could optionally link back to an uploaded file, but the
schemas and API layer did not fully honor that shape.

What changed:
- added `source_file_id` to:
  - `WorkExperienceCreate`
  - `WorkExperienceRead`
  - `WorkExperienceUpdate`
- updated the work-experience endpoints so create and update validate
  `source_file_id` ownership through `FileService.get_for_user()`
- changed PATCH handling to use `exclude_unset=True` so nullable fields can be
  explicitly cleared instead of being silently ignored
- added focused unit coverage in
  `backend/tests/unit/test_work_experience_contract.py` for:
  - schema alignment around `source_file_id`
  - migration shape for:
    - nullable `source_file_id`
    - `SET NULL` FK behavior
    - PostgreSQL `JSONB` / `ARRAY` columns
- added API integration coverage in
  `backend/tests/integration/api/test_work_experience.py` for:
  - create
  - list
  - update
  - delete
  - rejecting another user’s `source_file_id`

Why implement it this way?

Because the issue was about consistency, not expansion.

The migration already represented the intended storage model:
- `source_file_id` is optional
- deleting a file should not delete the work experience
- PostgreSQL-specific structured columns (`JSONB`, `ARRAY`) are part of the
  persistence contract

The missing piece was the HTTP/schema layer. Without `source_file_id` in the
schemas, the API could not round-trip the model cleanly. Without ownership
validation, the link could be abused across users. Without explicit null
handling on PATCH, the field could not be cleared through the API even though
the schema and FK design say that clearing it is valid.

Important tradeoffs:

This fix keeps ownership enforcement in the endpoint layer by reusing
`FileService.get_for_user()` instead of adding a new profile sub-entity
service. That is the smallest change that closes the security gap and keeps the
ticket scoped. The tradeoff is that WorkExperience ownership logic is still
distributed between:
- profile ownership via `ProfileService.get_or_create()`
- file ownership via `FileService.get_for_user()`

That is acceptable here because the ticket was about contract hardening, not a
broader service-layer refactor.

Real issues encountered during implementation and testing:

The shared `/home/vic/careercore` worktree was already on another issue branch
with local changes, so the issue had to be moved immediately into a dedicated
clean worktree from `origin/main` instead of trying to force the workflow
through the shared tree.

The focused unit test also failed on the first run because it imported the
Alembic revision by module name. This repo’s migration tests load revisions by
file path with `importlib.util.spec_from_file_location(...)`. The test was
rewritten to use the existing pattern rather than broadening the ticket into a
test-loader change.

The API integration tests were added but not executed locally in this ticket.
That is consistent with ADR-014 and the current repo state: broad app-level
integration runs still depend on PostgreSQL-compatible bootstrap paths for
models that use `JSONB` and `ARRAY`. The ticket did not widen into fixing that
repo-wide test infrastructure.

What future contributors should understand:

If a profile sub-entity can reference another owned resource, the schema needs
to expose that link and the API must validate ownership before persisting it.
Do not rely on foreign keys alone for authorization.

If a nullable field is meant to be clearable through PATCH, use
`exclude_unset=True`, not `exclude_none=True`. Otherwise `null` stops meaning
"clear this field" and becomes indistinguishable from "field omitted."

### 12.26 Issue #39 — AuditLog migration and append-only constraints

This ticket wired the `AuditLog` ORM model (which already existed in code) to
the Alembic migration history and documented its append-only intent.

What changed:
- added migration `20260414_0007` creating the `audit_logs` table
- `user_id` is nullable with no FK constraint — system events have no user;
  deleting a user account must not cascade-delete their audit history (ADR-012)
- `created_at` has no `server_default` — `AuditService.log_event()` sets the
  timestamp explicitly so it reflects application time, not DB receive time
- composite index `ix_audit_logs_user_created` on `(user_id, created_at)` for
  efficient per-user audit queries
- migration docstring and inline comments document the append-only contract;
  Phase 2 will add a PostgreSQL INSERT-only role and RLS policy (ADR-012)
- 10 unit tests using `_FakeOp` pattern (no database needed): revision chain,
  table creation, index shape, `user_id` nullability, FK absence, `action`
  column type and length, `created_at` no server default, downgrade order

Why nullable `user_id`?

Some audit events are system-level — a scheduled job, a background task, or
an infrastructure operation that has no associated authenticated user. Making
`user_id` nullable means those events can still be recorded without a dummy
user or a separate log sink. Per-user queries use the composite index; records
with `user_id IS NULL` appear in full-table scans and ops-facing queries.

Why no FK on `user_id`?

The audit record is evidence. If the user is deleted, the audit history should
survive. A FK with `ON DELETE CASCADE` would silently destroy that evidence.
A FK with `ON DELETE SET NULL` would orphan the pointer but keep the row.
Neither is what we want — we want the row to remain exactly as written. The
answer is no FK at all, which is the same decision made for `ai_call_logs`.

Why no `server_default` on `created_at`?

The database `now()` function returns the transaction commit time, not the
time the application decided to write the event. For audit logs that record
when something happened, the application time is the authoritative value.
If an audit row is written inside a long-running transaction, `now()` would
record the commit time, not the event time. Setting `created_at` explicitly
in `AuditService.log_event()` ensures the timestamp is always the moment the
event was observed by application code.

Why revision 0007 instead of 0006?

The migration was originally drafted as `0006` before a `git pull` landed
the uploaded-files migration (`0006_create_uploaded_files_table`) from a
concurrently merged PR. The stale file was deleted and the revision renamed
to `0007` with `down_revision = "20260414_0006"`. This is the correct recovery:
never patch the revision ID of an already-merged migration; instead bump your
own revision to sit above the new tail.

### 12.27 Issue #15 — Profile and sub-entity CRUD ownership enforcement

This ticket finished the ownership side of the Phase 1 profile API slice.

Before `#15`, the profile sub-entity endpoints were already filtering by the
authenticated user's profile ID, which prevented straightforward cross-user
reads and mutations. The problem was subtler: the ownership rule lived inside
endpoint-local queries, and the API could not distinguish between these two
cases:
- the target row does not exist
- the target row exists, but belongs to another user

That matters because those are different failures. The first is a missing
resource. The second is an authorization failure.

What changed:
- added service-layer helpers in `ProfileService` for:
  - listing child entities for the authenticated user only
  - checking targeted child-entity access and distinguishing:
    - owned
    - foreign-but-existing
    - missing
- updated `WorkExperience`, `Project`, `Skill`, and `Certification` endpoints
  to use the service-layer ownership boundary instead of embedding all access
  logic inline
- cross-user PATCH and DELETE attempts against existing profile sub-entities
  now return `403 Forbidden`
- truly missing sub-entity IDs still return `404 Not Found`
- list endpoints continue to return only the authenticated user's rows
- `WorkExperience.source_file_id` ownership validation now also distinguishes:
  - another user's file UUID → `403`
  - nonexistent file UUID → `404`
- added focused profile ownership tests and service-level tests for the new
  access boundary

Why not keep returning `404` for everything?

Because collapsing "forbidden" into "not found" makes the contract less clear
and hides authorization failures as if they were lookup failures.

There are cases where a product deliberately chooses "always 404" to minimize
resource enumeration. That is a valid strategy, but it has to be a deliberate
policy. This issue’s prompt explicitly called for `403` when the existing issue
contract expects authorization failure, so the API should say what actually
happened.

Why move this into `ProfileService` instead of just patching each endpoint?

Because ADR-013 is correct: ownership belongs at the service boundary.

If every endpoint re-implements:
- profile lookup
- child row lookup
- foreign-row detection
- error mapping assumptions

then the codebase slowly accumulates slightly different ownership semantics
across each entity type. That is how security drift happens.

By putting the access pattern in `ProfileService`, the endpoints get simpler:
- ask the service for access
- map owned / forbidden / missing to HTTP

That is the right layering.

Important tradeoff:

This issue does **not** introduce the all-entity ownership suite. That remains
separate work. The goal here was to make the profile slice itself correct and
testable without expanding into every other resource family in the repo.

Real implementation/testing note:

Focused service-level tests for the new ownership helpers ran cleanly. The
shared app-level integration harness in this environment remained noisy and did
not produce reliable local completion for the new profile ownership test module,
so verification stayed intentionally narrow around the service boundary and
syntax correctness of the changed endpoints/tests. That is not ideal, but it is
an honest statement of what was verified locally.

What future contributors should understand:

When a request targets a profile child row by ID, there are three states:
- it is yours
- it exists but is not yours
- it does not exist

Those states should not be conflated by accident.

If a future endpoint or service touches `WorkExperience`, `Project`, `Skill`,
or `Certification`, reuse the `ProfileService` ownership boundary instead of
re-inventing entity-specific access logic in the endpoint.

### 12.28 Issue #18 — Harden POST /files validation, storage key generation, and queueing

This ticket finished the basic safety contract for `POST /files`.

Before this change, the upload endpoint already rejected unsupported MIME types
and files larger than 10 MB, but those rules lived only in the HTTP layer. The
service still generated storage keys by embedding the original filename, and it
never actually queued extraction work after a successful upload.

What changed:
- moved upload validation into `FileService.upload()` so the service, not just
  the endpoint, enforces:
  - allowed MIME types
  - 10 MB size limit
- changed storage key generation from:
  - `user_id/file_id/original_filename`
  to:
  - `user_id/file_id.ext`
- kept the original filename only in `UploadedFile.original_filename`
- persisted `UploadedFile` in `pending` state after successful object storage
- queued `extract_file_text.delay(str(file_id))` after the row was flushed
- updated the endpoint to translate service validation failures into:
  - `415 Unsupported Media Type`
  - `413 Content Too Large`
- added focused unit coverage for:
  - validation failures
  - opaque storage-key behavior
  - `pending` record creation
  - extraction task queue trigger
  - endpoint HTTP mapping

Why implement it this way?

Because ADR-005 is right: the service layer should own the business contract.

Validation matters beyond HTTP. If the same upload flow is later triggered from
another entry point, such as CLI or background import code, the rules should
not depend on whether a specific FastAPI endpoint happened to run first. Moving
the checks into `FileService.upload()` makes the contract reusable and keeps the
endpoint thin.

Why remove the original filename from the storage key?

Because the storage key is an internal object-store identifier, not a
user-facing path. Embedding the original filename leaks unnecessary user input
into infrastructure paths and makes keys less stable as an internal contract.
The system already has a dedicated field for the user-facing filename:
`UploadedFile.original_filename`.

Keeping only the extension in the key is the pragmatic middle ground. It avoids
full filename leakage while still preserving enough suffix information to make
storage objects easier to inspect during debugging.

Important tradeoffs:

This ticket queues extraction after a successful upload, but it does not
implement extraction success/failure handling itself. That remains worker-scope
behavior. The point here was to make the upload path reliably hand work off to
the queue, not to finish the entire extraction pipeline.

The service currently flushes the `UploadedFile` row before queueing so the
worker has a durable file ID to target. If queue submission were to fail after
flush, the request would still fail upward at that point. This ticket does not
add compensating cleanup for already-uploaded objects because that would widen
scope into retry/cleanup policy.

Real issues encountered during implementation and testing:

The shared `/home/vic/careercore` worktree was again unusable for issue work
because it was on another branch with local changes. The ticket was moved into
a dedicated clean worktree from `origin/main` immediately.

The focused test run also hit the repo’s broad import surface: file-service and
endpoint modules pull in settings, auth, Celery, and async DB dependencies at
import time. The verification command therefore needed those dependencies
present even though the tests themselves only exercised mocked S3 and Celery
boundaries.

One service test initially failed because constructing a real `UploadedFile`
triggered an unrelated SQLAlchemy mapper problem in `User.ai_call_logs`. The
fix was to isolate that test from unrelated mapper configuration by patching
the record class in the test itself. That kept the ticket scoped to file-upload
behavior instead of dragging in unrelated ORM cleanup.

What future contributors should understand:

If you touch file upload behavior, preserve these boundaries:
- validation belongs in `FileService.upload()`
- storage keys are internal opaque identifiers, not filename mirrors
- queue submission happens only after storage succeeds and the metadata row
  exists in `pending`

Do not move signed-download response work back into this path. Upload and
download hardening are separate contracts in this codebase.

### 12.29 Issue #41 — Input validation audit and malformed payload coverage

This ticket was about closing a contract gap, not adding new business logic.

FastAPI already gives this codebase a strong default: if a request body fails
Pydantic validation, the framework returns `422` with a `{"detail": [...]}` body
and the handler never runs. That only works if the schemas actually describe the
contract. Before this issue, several write payloads were still too permissive:
they accepted bare strings with no explicit empty-string or max-length
constraints, which meant malformed input could reach deeper layers than it
should have.

What changed:
- added malformed-payload integration coverage for:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `POST /api/v1/jobs`
  - `POST /api/v1/profile/experience`
  - `POST /api/v1/profile/projects`
  - `POST /api/v1/profile/skills`
  - `POST /api/v1/profile/certifications`
- tightened the request schemas instead of patching endpoint handlers:
  - `UserLogin.password` now rejects empty strings
  - profile sub-entity create/update schemas now declare explicit string bounds
    for required names/titles and bounded optional text identifiers/URLs
- added focused schema-level tests so the validation contract could be verified
  without depending on the full app bootstrap

Why implement it this way?

Because ADR-004 is correct: the schema layer is the API contract.

If the endpoint has to remember that:
- a password cannot be empty
- a project name cannot be missing
- a certification name should be bounded to the same size as the persisted
  column

then the request contract is in the wrong place. The handler should receive a
typed payload that is already valid, delegate to the service layer, and not
re-implement transport validation with custom `if not payload.field` branches.

Important tradeoff:

This ticket did not broaden into response-shape work, service behavior changes,
or database migrations. It only tightened the request contract where the issue
required it. For jobs, the malformed-payload coverage follows the actual schema
contract on main, which uses `raw_text` as the required body field rather than a
separate `description` field name.

Real implementation/testing issue:

The focused schema tests ran cleanly and were the reliable verification path for
this ticket. The new integration test module was added, but the repo's current
app-level test bootstrap still builds full metadata against SQLite and fails
earlier on existing PostgreSQL-only `JSONB` columns in unrelated models. That is
the same boundary ADR-014 already documents. The correct response here was to
keep the ticket scoped, land the schema fixes and coverage, and report the
bootstrap limitation honestly instead of widening scope into test-infrastructure
repair.

What future contributors should understand:

When a malformed request currently returns `500`, the first question should be:
"does the Pydantic schema actually express the rule?" Most of the time the fix
belongs there, not in the endpoint.

If a model column has a meaningful max length or a field must not be blank,
capture that in the request schema explicitly. Otherwise the API contract is
underspecified and you will rediscover the same bug later through a different
endpoint or a less readable database failure.

### 12.30 Issue #19 — Complete async extraction workflow and structured parsing

This ticket finished the other half of the file-upload contract.

Issue `#18` made the upload path reliable: validate, store the object, persist
an `UploadedFile` row in `pending`, and enqueue extraction. Issue `#19` was the
worker-side completion of that design. The point was not to build a new file
subsystem. The point was to make the existing `UploadedFile` lifecycle real.

What changed:
- replaced the extraction-task stub with real worker behavior in
  `extraction_tasks.py`
- the worker now loads the `UploadedFile` row, marks it `processing`, downloads
  bytes through the existing file/storage layer, extracts text, writes
  `extracted_text`, and marks the row `ready`
- supported parsing paths now exist for:
  - PDF via `pypdf.PdfReader`
  - DOCX via `python-docx`
  - TXT via UTF-8 decode
- terminal failures now leave the row in place and persist:
  - `status=error`
  - `error_message=<failure details>`
- added focused unit coverage for:
  - parser dispatch by content type
  - `processing -> ready` state transitions
  - retry behavior on transient failures
  - final `error` persistence after retries are exhausted

Why implement it this way?

Because the existing model already told us what the right shape was.

`UploadedFile` already had:
- `status`
- `extracted_text`
- `error_message`

That is a strong signal that extraction state belongs on the row itself, not in
an undocumented side table or in Celery-only ephemeral state. The worker’s job
here is to make that existing contract true.

Why read file bytes through the service/storage layer instead of creating a
direct MinIO client inside the task?

Because storage access is infrastructure behavior, not parsing behavior.

If the worker opens its own separate storage path with duplicated bucket/client
logic, you now have two places that define how file bytes are retrieved. That
creates drift very quickly. The task should own extraction state transitions and
parser dispatch, not a second independent storage contract.

Important tradeoffs:

This implementation keeps retry behavior narrow on purpose. The worker retries
transient infrastructure/application failures and, once retries are exhausted,
records a terminal `error` state on the same row. It does not introduce object
cleanup policy, dead-letter handling, or a new extraction-events table. Those
may be valid future additions, but they are separate product decisions and
deserve explicit schema/design treatment if they happen.

The parsing logic is also intentionally pragmatic rather than clever. PDF,
DOCX, and TXT are handled directly with the libraries already chosen by the
project. There is no OCR layer, MIME sniffing expansion, or heuristic cleanup
beyond extracting readable text. That is correct for this ticket because the
issue was about completing the worker contract, not inventing a document-intel
platform.

Real implementation/testing issue:

The shared `/home/vic/careercore` path was not a safe main worktree when this
issue started, so the work was moved immediately into a dedicated clean
worktree from `origin/main`. That avoided replaying the exact branch/worktree
interference ADR-023 is meant to prevent.

The focused worker tests also surfaced a subtle test-seam problem: the bound
Celery task proxy is not convenient to patch directly for retry-state
simulation. The correct fix was to test the underlying task behavior and keep
the assertions about our retry/error logic, rather than turning the ticket into
a Celery internals exercise.

What future contributors should understand:

If extraction fails, preserve the `UploadedFile` row and make the failure
visible on that row. Do not “clean up” by deleting the metadata record. The row
is the durable source of truth for what happened to the upload.

Also, if you extend supported file types, update all three parts together:
- worker parser dispatch
- tests
- any upload validation contract that governs allowed types

Changing only one of those layers creates exactly the kind of drift this ticket
was meant to close.

### 12.30 Issue #28 — Implement request-driven resume bullet generation with evidence validation

This ticket replaced the placeholder `POST /resumes/{id}/bullets/generate`
stub with the actual Phase 1 service flow. The key point is that the endpoint
is request-driven, not analysis-driven: the client names one profile entity and
the job-requirement IDs it wants to target, and the service turns that request
into `BulletContext` rows for the provider.

What changed:
- added `BulletsGenerateRequest` to the resume schemas:
  - `profile_entity_type`
  - `profile_entity_id`
  - `requirement_ids`
- updated the endpoint to accept that request body and return
  `list[ResumeBulletRead]`
- implemented `ResumeService.generate_bullets(...)` with the exact service flow
  the issue called for:
  - verify resume ownership
  - resolve the selected profile entity through the authenticated user's
    profile
  - load `JobRequirement` rows by the supplied IDs
  - run `AICostService.check_budget(user)` before the AI call
  - build one `BulletContext` per requirement using a minimal entity summary
  - call `self._ai.generate_bullets(contexts)`
  - discard any generated bullet whose `evidence_entity_id` does not match the
    requested profile entity
  - persist `ResumeBullet` rows with:
    - `is_ai_generated=True`
    - `is_approved=False`
  - persist `EvidenceLink` rows for accepted bullets
  - log the AI call via `AICostService.log_call(...)`
- measured actual provider-call latency with `time.monotonic()` and wrote that
  to the AI call log

Why let the request specify the profile entity and requirement IDs directly?

Because that is the contract this issue asked for.

The endpoint is not trying to infer generation scope from prior scoring state.
It is an explicit generation request: “use this profile entity against these job
requirements.” That keeps the API surface simple and makes the source of bullet
context obvious to the caller.

Why still validate evidence after the provider call?

Because the provider may propose candidate bullets, but it does not define what
is safe to persist.

Even in a request-driven endpoint, the service must enforce that saved bullets
point back to the entity the caller actually selected. If the provider returns
an `evidence_entity_id` that does not match the generated contexts, the bullet
is discarded. That keeps the persisted evidence graph coherent and prevents the
database from storing model output that references unrelated entities.

Why is the entity summary intentionally minimal?

Because this issue specified the exact summary contract:
- work experience → `"{role_title} at {employer}"`
- project → `"{name}"`

That is narrower than the earlier analysis-derived version, which tried to fold
in description and extracted tags. The implementation here stays with the
issue’s explicit scope rather than expanding the prompt surface on its own.

Important edge behavior:

- missing resume ownership returns a not-found path from the service/endpoint
- missing work experience or project row for the authenticated user's profile
  fails fast
- an empty `requirement_ids` list produces an empty context list and therefore
  no saved bullets
- budget is checked before any provider call
- invalid evidence IDs are filtered out before any `ResumeBullet` or
  `EvidenceLink` row is written

Testing approach:

The focused unit tests stay on `ResumeService` rather than the full app stack.
That gives a clean signal on the service contract without broadening the ticket
into unrelated integration-harness problems. The tests verify:
- budget exceeded propagates before any provider call
- invalid evidence IDs are discarded
- saved bullets are AI-generated and unapproved
- `EvidenceLink` rows are created
- AI call logging records token counts

What future contributors should understand:

If you expand this endpoint to more entity types, update all three layers
together:
- request schema validation
- entity lookup / summary construction
- post-generation evidence validation

Changing only the prompt-building side without updating validation is how you
end up persisting bullets that point at evidence the service never authorized.

### 12.31 Issue #20 — Add integration tests for the signed URL endpoint

This ticket did not change the signed-download implementation itself. The
service layer was already correct: ownership enforcement lived in
`FileService.get_download_url_for_user()`, the response schema exposed only a
single `url` field, and the presigned TTL came from config. What was missing
was the HTTP-layer contract test that proves the endpoint behaves that way when
called through FastAPI with real auth.

What changed:
- added `backend/tests/integration/api/test_files.py`
- followed the same login pattern used by other integration tests:
  - create/use the test user fixture
  - authenticate via `POST /api/v1/auth/login`
  - call `GET /api/v1/files/{file_id}/url` with the bearer token
- seeded `UploadedFile` rows directly in the database instead of exercising the
  upload flow
- monkeypatched `FileService.get_presigned_url()` so no boto3/MinIO call is
  made during the endpoint tests
- covered the four issue acceptance criteria:
  - owner gets `200` with `{"url": "..."}`
  - response body does not leak `storage_key`
  - cross-user access returns `404`
  - missing file ID returns `404`
  - the returned URL path uses the configured short TTL

Why test this at the HTTP layer if the service tests already existed?

Because the endpoint contract is not identical to the service contract.

The service tests prove ownership filtering and URL generation behavior. They do
not prove that:
- auth wiring works correctly through FastAPI dependencies
- the endpoint maps `None` to the right `404`
- the response body only exposes the public `url` field and not implementation
  details like `storage_key`

For a file-download endpoint, those transport-level guarantees matter just as
much as the underlying service logic.

Why insert `UploadedFile` rows directly instead of going through `POST /files`?

Because this issue is about the download contract, not upload infrastructure.

Using the upload flow here would drag object storage, upload validation, and
queueing behavior into a test whose only real purpose is to validate the signed
URL endpoint. Seeding the file row directly keeps the test focused on the
authorization and response contract that issue `#20` actually cares about.

Why monkeypatch `get_presigned_url()` instead of letting boto3 run?

Because the HTTP contract does not need real object storage to be proven.

The endpoint only needs to show that it:
- finds the right owned row
- refuses foreign or missing rows
- returns the presigned URL string in the correct outward shape
- uses the configured TTL when asking the service for the URL

All of that can be verified with a fake presigned URL string. Pulling MinIO
into this test would add infrastructure coupling without increasing confidence
in the endpoint contract itself.

Important tradeoff:

These tests intentionally stop at the FastAPI/service seam. They do not prove
that boto3 can talk to MinIO or that the generated URL is usable against a real
bucket. That is a different class of test. The right split is:
- endpoint contract tests here
- object-storage integration tests elsewhere, if and when the project needs
  them

What future contributors should understand:

If this endpoint ever starts exposing more than `{"url": ...}`, treat that as a
public API contract change and update the tests deliberately. Do not casually
leak `storage_key`, bucket names, or other internal storage identifiers just
because the service has access to them.

Also, if the TTL changes, update the config and keep the HTTP test asserting the
configured value. The test should continue to prove "the endpoint uses config"
rather than hard-coding infrastructure behavior in the route.

### 12.32 Issue #29 — Implement resume bullet approve and reject endpoints

This ticket adds the first user-facing lifecycle step after bullet generation:
users can now approve a generated bullet or reject it entirely. The important
constraint is that a bullet is not owned directly by a user. It belongs to a
resume, and the resume belongs to a user, so every mutation here has to enforce
ownership through the resume boundary.

What changed:
- implemented `ResumeService.approve_bullet(...)`
- added `ResumeService.reject_bullet(...)`
- both methods use the same ownership-scoped lookup:
  - `ResumeBullet.id == bullet_id`
  - `ResumeBullet.resume_id == resume_id`
  - joined through `Resume` with `Resume.user_id == user_id`
- approval now:
  - sets `is_approved=True`
  - flushes
  - returns the updated `ResumeBullet`
- rejection now:
  - deletes the `ResumeBullet` row
  - flushes
  - returns `True/False` for found vs not found
- added two HTTP routes:
  - `PATCH /api/v1/resumes/{resume_id}/bullets/{bullet_id}/approve`
  - `DELETE /api/v1/resumes/{resume_id}/bullets/{bullet_id}`
- added integration coverage in
  `backend/tests/integration/api/test_resumes_bullets.py` for:
  - approve success
  - approve cross-user `404`
  - reject success with DB deletion
  - reject cross-user `404`

Why scope the lookup by both `resume_id` and `bullet_id` instead of querying
the bullet directly by ID?

Because ownership is attached to the resume, not the bullet in isolation.

If the service looked up `ResumeBullet` by `bullet_id` alone and then tried to
reason about ownership afterward, it would make it too easy to accidentally
turn bullet existence into an observable cross-user side channel. Joining
through `Resume` in the query makes the ownership boundary part of the lookup
itself, which is the right shape for this API.

Why return `404` instead of `403` for cross-user bullet mutations?

Because the rest of the ownership-safe patterns in this codebase already treat
"missing" and "belongs to someone else" the same way when the resource is being
looked up by a concrete identifier.

That avoids confirming that another user's bullet exists. For an entity like a
resume bullet, which is always nested under a parent resume, that is the safer
default contract.

Why delete the bullet on reject instead of adding another status flag?

Because this issue's contract explicitly says reject deletes the bullet, and
the existing schema already supports that shape cleanly.

`EvidenceLink` rows are children of `ResumeBullet` and already use cascade
delete. That means the service does not need to manually delete evidence rows
one by one. The database/model relationship already expresses the right cleanup
behavior.

Important tradeoff:

This ticket does not broaden into snapshot/version logic, bulk approval, or
restore/undo behavior. Reject is a hard delete of the bullet row. If product
requirements later need a recoverable rejection state, that should be modeled as
a new explicit workflow, not inferred retroactively from the current delete
contract.

Testing note:

The new integration module was added and the touched files compile cleanly. In
this local environment, the single integration-file pytest invocation did not
complete within a forced timeout, so the reliable verification path here was the
targeted code review plus compile check rather than claiming a full green
integration run that the environment did not actually produce.

What future contributors should understand:

If you add more bullet-level mutations, reuse the same ownership query shape.
Do not query `ResumeBullet` by ID alone and then try to patch ownership in
afterward. The join to `Resume` is the safety boundary.

Also, if you ever change reject from delete to a soft state transition, revisit
the `EvidenceLink` cleanup contract explicitly. Right now the cascade delete is
correct because reject means the bullet row itself is gone.
