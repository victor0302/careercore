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
