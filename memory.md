# CareerCore — Working Memory

This file is the short-form operational memory for the repository. It records
what changed, what was learned, and what future agents should check before
touching the same area again.

---

## 2026-04-14 — Issue #21: Job description and requirement migrations

**What was implemented**

- Added `JobRequirement` ORM model and connected it to `JobDescription`
- Added Alembic revision `20260414_0003a` for:
  - `job_descriptions`
  - `job_requirements`
  - `jobrequirementcategory` enum
- Re-pointed `20260414_0004_create_job_analysis_tables` so it depends on
  `20260414_0003a`
- Added migration-shape unit tests for the new revision and the updated
  `0004` dependency

**Why it mattered**

The repo already had a later job-analysis migration that referenced
`job_descriptions`, but no earlier migration actually created that table. That
meant the fresh-database migration story was incomplete even though parts of
the ORM and later migrations looked finished.

The fix was not just "add a table." The fix was to restore a correct revision
order so the schema can be built from scratch without hidden assumptions.

**Verification used**

- `python -m py_compile` on the touched model, migration, and test files
- isolated migration test run with:

```bash
PYTHONPATH=/tmp/careercore-issue21/backend uv run --no-project --with pytest --with sqlalchemy --with alembic python -m pytest --noconftest /tmp/careercore-issue21/backend/tests/unit/test_job_description_migrations.py /tmp/careercore-issue21/backend/tests/unit/test_job_analysis_migrations.py -q
```

**Problems encountered**

- The shared `/home/vic/careercore` worktree could not safely run
  `git pull origin main` because it already had unrelated modified and
  untracked files from other work.
- That local state was likely from concurrent agent activity and previous
  branches, so the issue work moved into a clean dedicated worktree:

```bash
git worktree add /tmp/careercore-issue21 -b issue-21-job-description-requirement-migrations origin/main
```

- Plain `pytest` was unavailable in the shell.
- The normal `uv run pytest` path failed because the backend packaging config
  still references `setuptools.backends.legacy:build`.

**What to remember next time**

- For migration work, trust a clean worktree more than a busy shared checkout.
- If another agent has touched the repo recently, inspect `git status` before
  running the default branch workflow in place.
- If the normal test runner fails in packaging/bootstrap before your new code
  even loads, isolate the migration/module tests rather than broadening the
  issue to fix unrelated infrastructure.
