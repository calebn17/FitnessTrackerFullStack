# CLAUDE.md — fitness-backend

This is the **authoritative** CLAUDE.md for the `fitness-backend/` stack. It overrides the repository-root CLAUDE.md for backend-specific commands and rules.

## Constraints

- Do NOT run `git push`.
- Do NOT install dependencies (`pip install`, `uv sync`, etc.).
- Do NOT access `.env` files unless the user **explicitly** asks in the current chat.
  - Use `.env.example` and documented config sources instead.

## Context before plans and implementation

Before creating plans or implementing changes that touch architecture, APIs, or cross-cutting behavior, skim:

1. `Documentation/Fitness Platform - System Design.md` (repo root) — platform architecture
2. `documentation/System Design Docs/Backend Design Spec.md` — module layout and API boundaries (index + parts; redirect at `documentation/Backend Design Spec.md`)
3. `Documentation/Plans/Backend Implementation Plans.md` — phased roadmap

Trivial, localized edits may skip this.

## Commands

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

Single test file:
```bash
PYTHONPATH=. pytest tests/unit/test_user_service.py
```

Single test by name:
```bash
PYTHONPATH=. pytest -k "test_name"
```

## Local Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Or: `uv sync --extra dev`

## Architecture

**Modular monolith** — FastAPI, domain-driven. Current phase: **Phase 5** (derived metrics + Phase 4 workout CRUD) on Phase 3 auth and Phase 2 data layer.

```
app/
├── main.py              # create_app(); /health; api_v1 router includes
├── config.py            # Pydantic Settings (DATABASE_URL, SUPABASE_JWT_SECRET, etc.)
├── dependencies.py      # DI: get_db_session, get_settings, get_supabase_jwt_claims
├── core/
│   ├── database.py      # Async SQLAlchemy engine/session singletons; Base
│   ├── repository.py    # BaseRepository(session)
│   └── security.py      # JWT decode + get_supabase_jwt_claims
└── domains/
    ├── users/           # User model; GET /users/me
    ├── workouts/        # Workout → ExerciseSet, DerivedMetrics
    └── ai/              # Insight (AI evaluation pipeline)
```

Each domain: `models.py` → `schemas.py` → `repository.py` → `service.py` → `router.py`

## Database

PostgreSQL 15 (async via asyncpg), SQLAlchemy 2.0, Alembic migrations.

```bash
docker compose up -d postgres          # start Postgres only
docker compose exec postgres psql -U fitness -d fitness   # psql shell
```

| Setting  | Value |
|----------|-------|
| User     | `fitness` |
| Password | `fitness` |
| Database | `fitness` |
| Host     | `127.0.0.1` |
| Port     | `5433` |

Connection string: `postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness`

Environment variables for auth: `SUPABASE_JWT_SECRET` (required), `SUPABASE_JWT_AUDIENCE` (default: `authenticated`).

## Repository pattern

Extend `BaseRepository` from `app/core/repository.py`. Use `flush()` not `commit()` inside repository methods — let the caller commit. Use `selectinload` for eager loading.

## Testing

Tests require a live Postgres (`docker compose up -d postgres`). Key fixtures:

- `migrated_database` — session-scoped, runs `alembic upgrade head` once
- `db_session` — truncates tables before each test, rolls back after

Tests skip (not fail) if Postgres is unreachable.

**Tooling:** mypy strict, Ruff (`E, F, I, UP, B`), pytest asyncio auto mode.

## CI

GitHub Actions runs: `ruff check .` → `mypy app` → `alembic upgrade head` → `pytest`. All must pass.

## Detailed reference

See `documentation/CLAUDE.md` for expanded PostgreSQL operations, model relationships, and migration details.
