# CareerCore — Working Memory

Short operational notes for future sessions. This is not the ADR log and it is
not a replacement for `notes.md`. The goal is to preserve practical context
that helps the next person avoid repeating the same mistakes.

---

## 1. Working rule

When the repository state starts moving underneath an issue, stop treating the
shared worktree as authoritative.

Use a clean worktree from `origin/main`, move only the issue-scoped files into
it, and finish the ticket there. This is faster than trying to recover after
commits land on the wrong branch or after unrelated changes leak into the diff.

---

## 2. Issue Memory

### Issue #17 — UploadedFile migration

What was done:
- read `DECISIONS.md` before starting, including the SQLite/PostgreSQL split in
  ADR-014
- checked the issue with `gh issue view 17`
- created and used a clean issue worktree at `/home/vic/careercore-issue-17`
- added migration `20260414_0006_create_uploaded_files_table.py`
- added unit test `backend/tests/unit/test_uploaded_file_migration.py`
- pushed branch `issue-17-uploaded-file-migration`
- opened PR `#74`

What mattered:
- the ORM already defined the real design:
  - one `uploaded_files` table
  - one DB-enforced `filestatus` enum
  - extraction output stored directly on the file row
- no extraction companion table should be invented unless the ORM actually
  adopts one
- the migration had to replicate the shared UUID and timestamp mixins exactly,
  not approximately

Operational problems encountered:
- the shared `/home/vic/careercore` worktree was already on
  `issue-35-aicalllog-migration` with unrelated changes, so the normal
  checkout workflow was not safe there
- fetch/push operations hit the sandbox SSH config permission problem again,
  so the git network steps had to run outside the sandbox
- the first uniqueness assertion in the fake-op migration test was brittle
  because SQLAlchemy’s unbound table elements did not expose the inline unique
  constraint the way a bound table would

What to remember next time:
- migration backfill tickets should mirror the ORM that already exists; do not
  invent extra schema just because the prompt leaves room for it
- for fake-op Alembic tests, assert the contract at the column or op-call level
  if SQLAlchemy’s unbound constraint objects are incomplete
- if the shared worktree is already dirty or on another issue branch, move the
  ticket into a dedicated clean worktree immediately

### Issue #22 — Job analysis and requirement-match migrations

What was done:
- read `DECISIONS.md`
- checked the issue with `gh issue view 22`
- synced `main`
- created and used a clean issue worktree to add migration
  `20260414_0004_create_job_analysis_tables.py`
- added focused migration tests for revision chain, JSONB, enum wiring, FK
  shape, indexes, and downgrade behavior
- left scoring logic and API behavior unchanged

What mattered:
- the ticket was about migration/model parity only
- `score_breakdown` had to stay PostgreSQL `JSONB`
- `match_type` had to be DB-enforced through the `matchtype` enum
- fresh-database safety was represented here by migration-structure coverage,
  not by broad unrelated backend tests

Operational problems encountered:
- the shared `/home/vic/careercore` worktree changed branch context during the
  task and picked up an unrelated `DECISIONS.md` change
- other issue branches and agent activity had already made the shared tree
  unreliable as a clean boundary
- the solution was to continue in `/home/vic/careercore-issue-22` instead of
  forcing the issue through the drifting shared worktree

What to remember next time:
- if another agent or shell is active, do not trust the current branch name in
  one worktree to remain stable
- if the worktree drifts, replay the issue into a dedicated clean worktree
  immediately
- keep migration tickets small; do not "bundle in" model behavior changes just
  because the same tables are involved

### Issue #21 — Job description and requirement migrations

What was done:
- read `DECISIONS.md`
- checked the issue with `gh issue view 21`
- created and used a clean issue worktree to add:
  - `JobRequirement`
  - migration `20260414_0003a_create_job_description_and_requirement_tables.py`
  - migration-shape tests for the new revision and the updated `0004` revision
- updated `20260414_0004_create_job_analysis_tables.py` so its dependency chain
  points at the new prerequisite migration

What mattered:
- this ticket was about restoring a correct fresh-database migration path, not
  about parse flow or scoring behavior
- `job_requirements.category` had to be DB-enforced through the
  `jobrequirementcategory` enum
- the revision chain itself was part of the bug; adding a migration file alone
  was not enough

Operational problems encountered:
- the shared `/home/vic/careercore` worktree could not safely run the standard
  `main` sync step because unrelated modified and untracked files were already
  present
- concurrent branch activity from other agents made the shared tree unreliable
  as an isolation boundary
- the solution was to continue in `/tmp/careercore-issue21` instead of forcing
  the issue through the drifting shared worktree
- the normal `uv run pytest` path hit an unrelated packaging problem in
  `backend/pyproject.toml` (`setuptools.backends.legacy:build`)

What to remember next time:
- if a migration issue depends on "fresh clone" behavior, do the work in a
  clean worktree first
- if later migrations already reference missing tables, repair the Alembic
  dependency chain explicitly
- when the standard test bootstrap fails before your new code loads, isolate
  the module-level migration tests rather than broadening the ticket to fix
  unrelated packaging work

### Phase 1 audit — 2026-04-26

What was done:
- audited the full codebase after PRs #119, #120, #121, #122 landed
  (job detail page, Terraform, resume workflow, AI provider resolver)
- compared the closed issue set (E0–E9, 103+ issues) against actual code state
- identified six gaps not covered by the original issue set
- created GitHub issues #127–#132

What mattered:
- every backend epic is complete; all gaps are frontend-side or a backend bug
- issue #127 (silent Celery exception swallowing) and #128 (logout not calling
  backend) are the only ones with correctness and security consequences
- issues #129–#132 are UX and quality work
- recommended fix order: #128 → #127 → #129 → #130 → #131 → #132

What to remember next time:
- before declaring a phase complete, do a focused audit against the original
  epic acceptance criteria and scan for: TODO comments, `alert(...)`, bare
  `except: pass`, functions exported from hooks that are never called anywhere,
  CI jobs that pass with zero test files
- concurrent worktrees for the four preceding PRs (#119–#122) worked without
  merge conflicts because each touched disjoint areas (frontend/app/jobs,
  infra/terraform, frontend/app/resumes, backend/app/ai) with the single
  exception of frontend/src/types/index.ts, which required a manual merge
