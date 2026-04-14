# CareerCore — AI Career Intelligence Platform

CareerCore is an open-source, AI-powered career intelligence platform that helps job seekers
build evidence-backed resumes, score job fit with explainable reasoning, and close skill gaps
with personalized recommendations.

> **Status:** Phase 1 — Core infrastructure and scoring engine  
> **Capstone:** MSU Denver Senior CS Project

---

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/your-org/careercore.git
cd careercore

# 2. Copy and fill environment variables
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY and JWT_SECRET_KEY

# 3. Start the full stack
docker compose up --build

# 4. Verify health
curl http://localhost:8000/health
```

The app will be available at:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **MinIO Console:** http://localhost:9001

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 14 |
| UI | Tailwind CSS + shadcn/ui | latest |
| State / Data | TanStack Query | v5 |
| Backend | FastAPI | latest |
| ORM | SQLAlchemy (async) | 2.x |
| Database | PostgreSQL | 15 |
| Cache / Broker | Redis | 7 |
| Task Queue | Celery | latest |
| Object Storage | MinIO | latest |
| AI | Anthropic Claude (Haiku / Sonnet) | latest |
| Auth | JWT (python-jose) + bcrypt | — |
| Containerization | Docker + Compose | — |
| CI/CD | GitHub Actions | — |
| IaC | Terraform | — |

---

## Repository Structure

```
careercore/
├── backend/        FastAPI application + Celery workers
├── frontend/       Next.js 14 App Router application
├── cli/            Phase 2 — CareerCore CLI (typer)
├── infra/          Terraform IaC + helper scripts
├── docs/           Architecture and design documents
└── .github/        CI/CD workflows and issue templates
```

---

## Documentation

- [Contributing](CONTRIBUTING.md)
- [Phase 0 Design Docs](docs/phase-0/README.md)
- [Backend API Docs](http://localhost:8000/docs) (when running)
- [Environment Variables](.env.example)

## Route Access

CareerCore uses a default-deny API boundary: every non-public route must depend
on `get_current_user` and reject missing, invalid, or expired access tokens
with `401 Unauthorized`.

Public exceptions:
- `GET /health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`

Development-only public routes:
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

All other API routes are protected.

---

## Running Tests

```bash
# Backend (unit + integration)
cd backend && pytest tests/ -v

# Frontend
cd frontend && npm test

# Type checking
cd backend && mypy app/
cd frontend && npx tsc --noEmit
```

---

## License

MIT — see [LICENSE](LICENSE)
