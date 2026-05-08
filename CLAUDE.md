# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Constraints

- Do NOT run `git push`.
- Do NOT install dependencies (`pip install`, `uv sync`, etc.).
- Do NOT access `.env` files unless the user **EXPLICITLY** asks in the current chat.
  - This includes `.env`, `.env.local`, `.env.*`, and similar secret env files.
  - Use `.env.example` and documented config sources instead when possible.

## Context before plans and implementation

Before **creating an implementation plan**, **writing multi-step task lists**, or **implementing** changes that touch architecture, APIs, domains, or cross-cutting behavior, **read or skim** the docs below for alignment (do not rely on code alone for intent and boundaries):

1. **Global system design** — `Documentation/Fitness Platform - System Design.md` — platform architecture, data flow, API contracts, and product behavior.
2. **Stack design spec** — For **`fitness-backend/`**, `fitness-backend/documentation/Backend Design Spec.md`. For other stacks (future clients), read that stack’s design spec or `documentation/system_design.md` when present.
3. **CLAUDE.md (constraints and runbooks)** — Prefer the **most local** file for the work: `fitness-backend/documentation/CLAUDE.md` for backend commands and operational detail, then repository root `CLAUDE.md` (this file), then `.agent-harness/CLAUDE.md` for harness role and `harness` commands. **Stack-local wins** for that stack’s commands and rules when both exist.
4. **Phased roadmap (when applicable)** — If the task maps to a roadmap slice, skim the relevant section of `Documentation/Plans/` (e.g. `Documentation/Plans/Backend Implementation Plans.md`).

**Depth:** Use **targeted skimming** (headings, sections for the domains or surfaces you will change) unless a full read is requested. **Trivial, localized edits** may skip this when the goal is explicitly minimal change.

## Build & Development Commands

All commands run from `fitness-backend/`:

```bash
make dev          # docker compose up -d + uvicorn with reload on :8000
make down         # stop docker containers
make lint         # ruff check .
make typecheck    # mypy app
make test         # PYTHONPATH=. pytest
make migrate      # alembic upgrade head
make db-reset     # drop + recreate schema, then migrate
```

Run a single test file:
```bash
cd fitness-backend && PYTHONPATH=. pytest tests/test_health.py
```

Run a single test by name:
```bash
cd fitness-backend && PYTHONPATH=. pytest -k "test_name"
```

## Architecture

**Modular monolith** — FastAPI backend under `fitness-backend/` with domain-driven structure:

```
fitness-backend/
├── app/
│   ├── main.py              # App factory (create_app)
│   ├── config.py            # Pydantic settings from .env
│   ├── dependencies.py      # FastAPI dependency injection
│   ├── core/                # Cross-cutting: database, middleware, security, logging, exceptions
│   ├── domains/             # Business logic organized by domain
│   │   ├── workouts/        # Workout logging (models, schemas, service, repository, router)
│   │   ├── users/           # User management
│   │   ├── ai/              # AI evaluation pipeline (prompts, evaluation, pipeline)
│   │   └── sync/            # Offline-first sync
│   └── workers/             # Background tasks
├── alembic/                 # Database migrations (Phase 2+)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docker-compose.yml       # PostgreSQL 15 + Redis 7
```

Each domain follows the pattern: `models.py` → `schemas.py` → `repository.py` → `service.py` → `router.py`

All repositories extend `BaseRepository` from `app/core/repository.py`, which holds the async SQLAlchemy session. Database engine/session singletons live in `app/core/database.py`; tests use `reset_database_singletons()` and `init_database_engine()` to swap in a test DB URL.

**Infrastructure:** PostgreSQL (async via asyncpg), Redis, both managed via Docker Compose.

**Tooling:** Python 3.11+, Ruff (lint + format), mypy (strict mode), pytest with asyncio auto mode.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on changes to `fitness-backend/`:
1. `ruff check .`
2. `mypy app`
3. `pytest`

Always pass these three before considering work complete.

## Key Design Decisions

- **Offline-first sync** — iOS client uses SwiftData locally; sync domain handles eventual consistency.
- **AI evaluation pipeline** — Dedicated domain (`domains/ai/`) with prompt templates, evaluation logic, and pipeline orchestration.
- **Phased rollout** — Phase 1 is scaffold + health; later phases add auth, migrations, workers. Check `Documentation/Plans/` for current phase scope.

## Documentation

- `Documentation/Fitness Platform - System Design.md` — Full system architecture
- `fitness-backend/documentation/Backend Design Spec.md` — Backend module design
- `Documentation/Plans/Backend Implementation Plans.md` — Phased implementation roadmap
