# Contributing to CareerCore

Thank you for your interest in contributing! This guide covers everything you need to get started.

---

## Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+
- Git

---

## Local Development Setup

```bash
# Clone the repo
git clone https://github.com/your-org/careercore.git
cd careercore

# Set up environment
cp .env.example .env
# Fill in required values (see .env.example for guidance)

# Start dependent services only
docker compose up db redis storage storage_init -d

# Backend — run locally with hot reload
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend — run locally with hot reload
cd frontend
npm install
npm run dev
```

Or run everything in Docker:
```bash
docker compose up --build
```

---

## Branch Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-description>` | `feat/resume-bullet-generation` |
| Bug fix | `fix/<short-description>` | `fix/jwt-refresh-401` |
| Chore / infra | `chore/<short-description>` | `chore/update-dependencies` |
| Documentation | `docs/<short-description>` | `docs/scoring-algorithm` |

All branches should be cut from `main`.

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(resume): add bullet confidence scoring
fix(auth): handle expired refresh token gracefully
chore(deps): bump anthropic to 0.25.0
docs(scoring): document weight formula
```

---

## Pull Request Checklist

Before opening a PR, confirm:

- [ ] Branch name follows the convention above
- [ ] All existing tests pass locally (`pytest tests/ -v`)
- [ ] New logic has test coverage
- [ ] `ruff check backend/` passes with no errors
- [ ] `mypy backend/app` passes (strict mode)
- [ ] `npx eslint frontend/src` passes
- [ ] `npx tsc --noEmit` passes in `frontend/`
- [ ] No secrets, API keys, or `.env` files committed
- [ ] New endpoints include ownership checks (users can only access their own data)
- [ ] State-changing operations write to the audit log
- [ ] `docker compose up --build` still starts cleanly
- [ ] PR description uses the PR template and references a GitHub issue

---

## Code Style

**Python:**
- Formatter / linter: `ruff` (line length 100, E/W/F/I rules)
- Type checker: `mypy` in strict mode
- All async DB operations must use `async/await` — never call sync SQLAlchemy in an async context

**TypeScript:**
- Strict TypeScript — no `any` except where unavoidable (add a comment explaining why)
- ESLint with `@typescript-eslint/recommended`

---

## AI Usage Policy

- `AI_PROVIDER=mock` must be set in all test and CI environments
- Never call real AI APIs in tests — use `MockAIProvider`
- Every real AI call must pass through `AICostService.check_budget()` before execution
- Token usage must be logged in `AICallLog` after every call

---

## Questions?

Open a [GitHub Discussion](https://github.com/your-org/careercore/discussions) or file an issue using the Task template.
