---
tags:
  - project
  - fitness
  - backend
  - fastapi
  - python
  - architecture
title: Fitness Platform - Backend Design Spec
created: 2026-04-25
status: draft
---

# Fitness Platform - Backend Design Spec

> Global context: [Fitness Platform - System Design](../../../Documentation/Fitness%20Platform%20-%20System%20Design.md) (repo root)

**Entry for humans and agents:** this file is the **index only**. Detailed sections live in linked **part files** in this same directory so you can open just what you need.

---

## For coding agents

| Goal | Read first |
|------|------------|
| Orientation, stack choices, repo tree, domain layering | [Part 1 — Overview, structure, domains](Backend%20Design%20Spec%20-%20Part%2001%20Overview%20Structure%20Domains.md) |
| Models, engine/session, migrations | [Part 2 — Database](Backend%20Design%20Spec%20-%20Part%2002%20Database.md) |
| Routers, endpoint tables, request/response sketches | [Part 3 — API](Backend%20Design%20Spec%20-%20Part%2003%20API.md) |
| Offline sync (Phase 6 shipped) and AI (illustrative) | [Part 4 — Sync and AI](Backend%20Design%20Spec%20-%20Part%2004%20Sync%20and%20AI.md) |
| Auth, settings, errors, tests, metrics, deploy | [Part 5 — Operations](Backend%20Design%20Spec%20-%20Part%2005%20Operations.md) |

**Source of truth:** shipped behavior is always `fitness-backend/app/`, `alembic/`, and `tests/`, plus runbooks [`README.md`](../../README.md) and [`documentation/CLAUDE.md`](../CLAUDE.md). Large code blocks in Parts 4–5 are often **architecture sketches** for later phases, not guaranteed to match the repo line-for-line.

**Skim strategy:** read this page (2 minutes), then open **one** part file for the domain you are changing.

---

## Document map (all parts)

| Part | File | Sections |
|------|------|----------|
| 1 | [Backend Design Spec - Part 01 Overview Structure Domains.md](Backend%20Design%20Spec%20-%20Part%2001%20Overview%20Structure%20Domains.md) | §1 Overview · §2 Project structure · §3 Domain architecture |
| 2 | [Backend Design Spec - Part 02 Database.md](Backend%20Design%20Spec%20-%20Part%2002%20Database.md) | §4 Database layer |
| 3 | [Backend Design Spec - Part 03 API.md](Backend%20Design%20Spec%20-%20Part%2003%20API.md) | §5 API layer |
| 4 | [Backend Design Spec - Part 04 Sync and AI.md](Backend%20Design%20Spec%20-%20Part%2004%20Sync%20and%20AI.md) | §6 Sync protocol · §7 AI pipeline |
| 5 | [Backend Design Spec - Part 05 Operations.md](Backend%20Design%20Spec%20-%20Part%2005%20Operations.md) | §8 Auth · §9 Configuration · §10 Errors · §11 Testing · §12 Production hardening · §13 Observability · §14 Deployment · Next steps |

---

## Key decisions (summary)

| Aspect | Decision |
|--------|----------|
| **Framework** | FastAPI with Pydantic v2 |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Database** | PostgreSQL (Neon serverless) |
| **Auth** | Supabase Auth (JWT validation) |
| **Background jobs** | Redis + ARQ (fast follow — not needed for MVP) |
| **LLM** | Anthropic Claude API (fast follow) |

---

## On this page (index anchors)

- [For coding agents](#for-coding-agents)
- [Document map](#document-map-all-parts)
- [Key decisions](#key-decisions-summary)

---

## How to read the part files

Each part begins with a link back to this index. Inside a part, use your editor outline or search for `##` headings. Section numbers (1–13) match the original monolithic spec for stable references from plans and chat.
