# Phase 0 — Planning Documents

This directory contains the Phase 0 design corpus for CareerCore.
These 23 documents cover the full architecture, data model, security posture,
scoring algorithm, and CLI design created before any code was written.

## Document Index

| # | Topic |
|---|-------|
| 1 | Product Vision & Problem Statement |
| 2 | User Stories & Persona Map |
| 3 | System Architecture Overview (C4 Level 1 & 2) |
| 4 | Technology Stack Decision Log |
| 5 | Data Model — Entity Relationship Diagram |
| 6 | Data Model — Field-Level Specification |
| 7 | API Design — RESTful Endpoint Inventory |
| 8 | API Design — Request/Response Schema Reference |
| 9 | Authentication & Authorization Design |
| 10 | JWT Strategy & Refresh Token Rotation |
| 11 | AI Integration Architecture |
| 12 | AI Provider Abstraction Layer Design |
| 13 | Token Budget & Cost Control Strategy |
| 14 | Scoring Algorithm — Weight Formula & Evidence Map |
| 15 | Scoring Algorithm — Match Type Decision Tree |
| 16 | Resume Generation — Bullet Evidence Linking |
| 17 | Gap Analysis & Recommendation Engine |
| 18 | File Upload & Text Extraction Pipeline |
| 19 | Celery Task Queue Design |
| 20 | Audit Log — Append-Only Event Schema |
| 21 | Threat Model — STRIDE Analysis |
| 22 | Security Controls & OWASP Top 10 Mitigations |
| 23 | CLI Design (Phase 2) — Command Taxonomy |

## How to Use

These documents are the authoritative design reference for all Phase 1 implementation decisions.
When you encounter a `TODO` comment in the code, refer to the corresponding document above
for the full specification.

Ask your AI assistant to elaborate on any topic, e.g.:
- "Explain the scoring algorithm weight formula from doc 14"
- "Show the threat model for the file upload endpoint from doc 21"
- "Detail the token budget strategy from doc 13"
