# CareerCore Repo Health Review

**Date:** 2026-04-14  
**Scope:** Backend architecture, recent merged work, migration safety, test/CI posture, ownership/security posture, and current file/resume subsystem maturity.

## Executive Summary

The repository is in a meaningfully better state than a scaffold project. The
main branch is moving coherently, recent issue work has merged back into
`main`, and there are no obvious unresolved merge artifacts left in the tree.

The strongest implemented slice today is:
- auth
- profile foundation
- job description persistence
- AI-backed job parsing with budget enforcement
- deterministic scoring and job analysis read responses

The weakest slice today is:
- uploaded files / extraction
- resume generation / versioning
- some operational hardening around rate limits, validation, and platform setup

The biggest concrete technical concern right now is the migration dependency
gap around `uploaded_files`. The file and resume subsystems are not chaotic,
but they are still structurally incomplete.

## What Was Checked

This review checked:
- local git state and recent mainline history
- unresolved merge conflict markers
- open GitHub issues and PR state
- current ADR spine in `DECISIONS.md`
- backend repo layout and layer boundaries
- Alembic migration chain
- pytest bootstrap and DB session setup
- GitHub Actions workflows
- ownership and route protection patterns
- file and resume model/service/endpoint/test maturity

## Current Repo State

### Git / Merge Health

Findings:
- No unresolved merge conflict markers were found in `/home/vic/careercore`.
- GitHub currently showed no open PR backlog at the time of review.
- Recent merged work appears to have landed back on `main` instead of drifting
  in long-lived unmerged branches.

Recent merged work visible in history included:
- issue `#3` Anthropic provider implementation
- issue `#21` job description / requirement migrations
- issue `#22` job analysis / match-table migrations
- issue `#24` job parse persistence
- issue `#26` job analysis read responses
- associated documentation backfill work

Interpretation:
- merge conflict churn appears controlled
- the repo is being integrated continuously rather than stockpiling risky diffs
- the recent multi-agent workflow appears to have improved rather than harmed
  mainline coherence

### Architecture Coherence

The backend structure is healthy and understandable:
- `models/` hold ORM/database truth
- `schemas/` hold API/request/response contracts
- `services/` hold business logic
- `api/v1/endpoints/` remain thin request handlers
- `ai/` isolates provider abstractions and implementations
- `workers/` is the background task boundary

This is a good system shape.

Why this matters:
- security and ownership rules belong in service logic, not scattered across
  endpoints
- deterministic rules like scoring are kept in ordinary Python code and are
  therefore testable and auditable
- AI behavior is isolated behind a contract, which keeps the expensive and
  unstable parts of the system from bleeding into everything else

## ADR / Design Maturity

The ADR trail is now substantial and useful, not decorative. It covers:
- monorepo and stack choices
- model/schema separation
- service-layer boundaries
- AI provider protocol design
- deterministic scoring
- AI cost guards
- auth token design
- refresh token rotation
- append-only audit logging
- ownership enforcement
- test strategy
- issue workflow
- scoring evidence design
- route protection defaults
- signed URL constraints
- test bootstrap rules
- concurrent-agent worktree isolation
- job analysis persistence rules
- provider token usage contract
- migration ordering rules

Interpretation:
- the architecture has memory
- future contributors do not need to reverse-engineer all prior decisions from
  code alone
- this is a positive sign of engineering maturity

## Test and CI Health

### Test Bootstrap

Positive findings:
- `backend/tests/conftest.py` now sets environment variables before importing
  app modules
- `backend/app/db/session.py` now handles SQLite correctly by avoiding
  unsupported pool arguments

Why this matters:
- the repo previously had import-time settings coupling that could break tests
  before pytest even ran
- the current setup is materially better and aligns with the ADR that unit
  tests should run on SQLite and integration tests should run on PostgreSQL

Remaining concern:
- the test strategy is sound, but the real confidence level still depends on
  whether CI is consistently exercising the intended split and whether future
  contributors keep respecting that boundary

### CI Workflows

Positive findings:
- backend lint exists
- backend mypy exists
- backend tests run in CI
- frontend lint, typecheck, and tests exist
- Docker builds exist
- security scanning exists
- CI forces `AI_PROVIDER=mock` for backend tests

This is a good baseline for a project at this stage.

Remaining concerns:
- CI quality is only as good as the test coverage behind it
- some slices of the backend remain scaffolded, which means green CI does not
  imply the full product is finished
- platform issues around Docker / compose / health checks remain open as tracked
  product work

## Ownership and Security Posture

### What Looks Good

Route protection and ownership design are mostly solid:
- protected routes consistently use `get_current_user`
- service methods like `get_for_user()` and `list_for_user()` are used in the
  right places
- ownership filtering is happening in service queries rather than relying on
  endpoint-only checks
- signed URL access goes through owner-aware service logic

This is exactly the right pattern.

Why it matters:
- ownership bugs are some of the easiest ways to leak data in a multi-user app
- putting ownership logic in services makes the code safer by default

### Remaining Concerns

- The repo still needs a dedicated cross-entity ownership suite to prove these
  patterns hold across all resources, not just the slices already exercised.
- Input validation hardening is still tracked as open work and should not be
  treated as “done” simply because the main routes exist.

## Job Analysis Slice

This is currently the most mature product slice.

What is in place:
- job description persistence
- requirement persistence
- deterministic scoring
- matched and missing requirement persistence
- evidence maps
- job list/detail responses that expose analysis data
- budget check before parse provider call
- AI call logging for parse operations

Why this is strong:
- the middle of the product pipeline now has a real shape
- scoring is deterministic and evidence-backed
- parsing is moving through the intended AI provider and cost-control layers
- the read side exposes analysis outputs in a way the frontend can consume

Remaining concerns:
- some stale TODO comments still remain in endpoint docstrings even though
  behavior has already been implemented in the service layer
- this does not break functionality, but it creates maintenance confusion and
  should be cleaned up opportunistically

## Biggest Current Technical Risk

## Uploaded File Migration Gap

This is the clearest structural issue found in the repo.

Observed state:
- `backend/app/models/uploaded_file.py` defines the `uploaded_files` ORM model
- `work_experiences.source_file_id` and `projects.source_file_id` reference
  `uploaded_files.id`
- `backend/alembic/versions/20260413_0003_create_profile_tables.py` creates
  foreign keys to `uploaded_files.id`
- there is still no Alembic migration in the repo creating `uploaded_files`

Why this matters:
- ORM correctness is not enough
- a fresh database built only from Alembic history likely cannot reproduce the
  schema the code expects
- this is the kind of issue that can stay hidden in developer environments but
  fail in CI, new clones, or production bootstrap

Conclusion:
- issue `#17` is not optional bookkeeping
- it is required to restore migration-chain integrity

## Files Slice Review

### What Exists

The files subsystem is partially implemented:
- uploaded file ORM model exists
- upload endpoint exists
- signed URL endpoint exists
- owner-aware file lookup exists
- signed URL response hides `storage_key`
- unit tests cover ownership and basic signed URL contract behavior

### What Is Still Incomplete

1. No `uploaded_files` migration yet  
This is the foundational gap described above.

2. Storage keys are not opaque  
`backend/app/services/file_service.py` still generates keys as:

`user_id/file_id/filename`

That leaks the original filename and violates the intended storage contract.

3. Extraction queueing is still TODO  
The service documentation says extraction should be enqueued after upload, but
the implementation has not completed that path yet.

4. Extraction workflow itself is still TODO  
The worker pipeline remains unfinished.

### Practical Interpretation

The files slice has enough code to look present, but not enough to be called
complete. It is mid-construction.

If describing this to a junior engineer:

An endpoint existing does not mean the subsystem is done.  
For files, the system is only complete when:
- the table exists in migrations
- the upload contract is correct
- object keys are safe
- extraction is queued
- extraction actually runs

Right now, only part of that chain exists.

## Resume Slice Review

### What Exists

The resume domain model is already shaped:
- `Resume`
- `ResumeVersion`
- `ResumeBullet`
- `EvidenceLink`

Basic endpoints and service methods exist for:
- create resume
- list resumes
- get resume

The schema layer also exists for basic request/response types.

### What Is Still Scaffolded

The real product behavior is not implemented yet:
- generate bullets
- approve bullet
- snapshot version
- version listing
- version detail with evidence display
- resume migrations

The current code still contains `NotImplementedError` for the core workflow in
`backend/app/services/resume_service.py`.

### Practical Interpretation

This is an orderly incompleteness, not a broken design.

The system already knows what the resume data model should be. What is missing
is the behavior and persistence work that turns that model into a working user
flow.

That is a good place to be architecturally, but it still means the resume
subsystem is not close to production-ready.

## What the Existing Tests Suggest

### Stronger Areas

Tests are meaningfully covering:
- auth flows
- route protection
- job parse behavior
- job analysis read serialization
- file ownership checks
- signed URL response-shape behavior

This is consistent with the more mature backend slices.

### Thinner Areas

Tests are still thin or absent for:
- file upload hardening end-to-end
- extraction workflow
- resume generation and lifecycle
- broad ownership coverage across every entity family

This is expected because those behaviors are not yet fully implemented.

## Recommended Next Work

### Highest-Priority Sequence

To move the repo from “coherent partial system” toward “coherent end-to-end
system,” the next sequence should be:

1. issue `#17` — Create migration for `UploadedFile` and extraction metadata
2. issue `#18` — Harden `POST /files`
3. issue `#19` — Complete extraction Celery workflow
4. issue `#27` — Resume migrations
5. issue `#28` — Implement bullet generation with evidence validation
6. issue `#29` — Implement approve/reject endpoints
7. issue `#30` — Implement snapshot/save flow
8. issue `#31` — Implement version listing
9. issue `#32` — Implement version detail and evidence display

Why this order makes sense:
- it repairs the input side first
- then finishes the output side
- it builds on the stronger job-analysis middle of the system

### Concurrency Guidance

Recommended:
- one agent on `#17`
- one agent on `#18`
- keep `#19` behind those or start only when the schema and upload contract are
  stable
- start `#27` after the file migration base is no longer a risk

Avoid:
- stacking multiple migration-heavy issues concurrently unless the revision
  order has been coordinated explicitly

## Senior-Engineer Summary

The repository is in decent shape.

Mainline development appears coherent. The architecture is good. The core
system decisions are documented. The job-analysis slice has become real. The
recent merge/conflict problems appear to have been resolved cleanly.

The biggest remaining concern is not random code quality. It is that the file
and resume subsystems are still structurally incomplete, and the missing
`uploaded_files` migration is a real schema-integrity problem until fixed.

If the goal is to make the product feel end-to-end coherent, the right focus is
now:
- finish the file ingestion base
- then finish the resume generation/versioning path

## Intern-Friendly Summary

If you are new to the repo, the easiest mental model is:

The system already knows how to:
- store users and profiles
- authenticate them
- accept job descriptions
- parse jobs through AI
- score those jobs deterministically
- expose analysis results

The system does **not** fully know how to:
- safely finish the uploaded-file pipeline
- extract uploaded documents end-to-end
- turn evidence into resume bullets and saved resume versions

So the repo is not a mess.
It is a partially completed product with a clear center of gravity and a clear
next path.
