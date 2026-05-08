# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Constraints

- Do NOT run `git push`.
- Do NOT install dependencies (`pip install`, `uv sync`, etc.).

## Context before plans and implementation

Before **creating an implementation plan**, **writing multi-step task lists**, or **implementing** changes that touch architecture, APIs, domains, or cross-cutting behavior, **read or skim** the docs below for alignment (do not rely on code alone for intent and boundaries):

1. **Global system design** — `Documentation/Fitness Platform - System Design.md` (repository root) — platform architecture, data flow, API contracts, and product behavior.
2. **Backend design spec** — [`documentation/Backend Design Spec.md`](documentation/Backend%20Design%20Spec.md) — module layout and API boundaries. For other stacks (future clients), read that stack’s design spec or `documentation/system_design.md` when present.
3. **CLAUDE.md (constraints and runbooks)** — Prefer **this file** for backend commands, venv, Postgres, and tests; then repository root `CLAUDE.md` for the short repo-wide summary; then `.agent-harness/CLAUDE.md` for harness role and `harness` commands. **Stack-local wins** for this stack when both exist.
4. **Phased roadmap (when applicable)** — Skim the relevant section of `Documentation/Plans/` (e.g. `Documentation/Plans/Backend Implementation Plans.md`).

**Depth:** Use **targeted skimming** (headings, sections for the domains or surfaces you will change) unless a full read is requested. **Trivial, localized edits** may skip this when the goal is explicitly minimal change.

## Local Python environment

Use a project virtualenv so tools used by `make` (`ruff`, `mypy`, `pytest`) resolve from that environment:

```bash
cd fitness-backend
python3.12 -m venv .venv        # Python 3.11+ required by pyproject.toml
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Alternatively: `uv sync --extra dev` (uv manages its own environment).

Activate `.venv` (or use `uv run …`) before running the commands below.

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

Single test file (after activating `.venv` or with deps on `PATH`):

```bash
PYTHONPATH=. pytest tests/unit/test_repositories.py
```

Single test by name:

```bash
PYTHONPATH=. pytest -k "test_name"
```

## PostgreSQL (local Docker)

Postgres is defined in `docker-compose.yml` (image `postgres:15-alpine`). Run everything from `fitness-backend/`.

**Start / stop**

```bash
docker compose up -d postgres          # Postgres only (API not started)
docker compose ps                       # container status
docker compose logs -f postgres        # follow Postgres logs
docker compose stop postgres           # stop Postgres container
```

Use `make dev` to bring up **all** Compose services (Postgres + Redis) and start uvicorn; `make down` stops the stack.

**Migrations**

```bash
make migrate                           # alembic upgrade head
make db-reset                          # DROP SCHEMA public CASCADE + recreate + migrate (requires postgres container running)
```

**`psql` (interactive shell inside the container)**

```bash
docker compose exec postgres psql -U fitness -d fitness
```

**One-off SQL from the host (non-interactive)**

```bash
docker compose exec -T postgres psql -U fitness -d fitness -c "SELECT current_database(), current_user;"
```

**Connection defaults**

| Setting | Value |
|--------|--------|
| User | `fitness` |
| Password | `fitness` |
| Database | `fitness` |
| Host (from host machine) | `127.0.0.1` |
| Port | `5432` |

**App / Alembic URL** — `DATABASE_URL`; default async DSN: `postgresql+asyncpg://fitness:fitness@127.0.0.1:5432/fitness`.

**Port 5432 already in use** — Stop the other Postgres instance or change the host port mapping for the `postgres` service in `docker-compose.yml`.

## Architecture

**Modular monolith** — FastAPI backend with domain-driven structure. Current phase: **Phase 2 (Database & Models)**.

```
app/
├── main.py              # create_app() factory; /health endpoint
├── config.py            # Pydantic Settings (DATABASE_URL, DEBUG, etc.)
├── dependencies.py      # FastAPI DI (get_db_session)
├── core/
│   ├── database.py      # Async SQLAlchemy engine/session singletons; Base declarative class
│   └── repository.py    # BaseRepository(session) — base class for all repositories
└── domains/
    ├── users/           # User (supabase_id, email)
    ├── workouts/        # Workout → ExerciseSet, DerivedMetrics
    └── ai/              # Insight (pending → completed AI output)
```

Each domain follows: `models.py` → `schemas.py` → `repository.py` → `service.py` → `router.py`

## Database

**Stack:** PostgreSQL 15 (async via asyncpg), SQLAlchemy 2.0 ORM, Alembic migrations.

**Operational commands** (Compose, `psql`, migrate): see **PostgreSQL (local Docker)** above.

**Models and relationships:**
- `User` (1) → `Workout` (many) via `user_id`
- `Workout` (1) → `ExerciseSet` (many), `DerivedMetrics` (1), `Insight` (1)
- `ExerciseSet` and `DerivedMetrics` cascade-delete with `Workout`
- `Workout.client_id` — UUID from the iOS client, unique, used for offline deduplication

**Migrations** live in `alembic/versions/` named `phase2_0N_*.py`. Apply with `make migrate` (see **PostgreSQL (local Docker)**).

**Connection string** — set via `DATABASE_URL` env var; defaults to `postgresql+asyncpg://fitness:fitness@127.0.0.1:5432/fitness` in tests.

## Repository Pattern

All repositories extend `BaseRepository` from `app/core/repository.py`:

```python
class SomeRepository(BaseRepository):
    async def get_by_id(self, id: uuid.UUID) -> Model | None:
        return await self.session.get(Model, id)
```

Instantiate by passing an `AsyncSession`: `SomeRepository(session)`.

Use `flush()` (not `commit()`) inside repository methods — let the caller commit. Use `load_children=True` (via `selectinload`) when you need eager loading of relationships.

## Testing

Tests require a live Postgres instance (`docker compose up -d postgres`). The `migrated_database` session-scoped fixture runs `alembic upgrade head` once. The `db_session` fixture truncates all tables before each test and rolls back after.

```python
async def test_something(db_session: AsyncSession) -> None:
    repo = SomeRepository(db_session)
    obj = await repo.create(...)
    await db_session.commit()
    ...
```

Tests skip automatically (not fail) if Postgres is unreachable.

**Tooling:** mypy strict mode, Ruff with rules `E, F, I, UP, B`, pytest asyncio auto mode.

## Documentation

- [`documentation/Backend Design Spec.md`](documentation/Backend%20Design%20Spec.md) — Backend module layout and API boundaries
- Repository-wide architecture: `Documentation/Fitness Platform - System Design.md` (repo root)

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs `ruff check .` → `mypy app` → `alembic upgrade head` → `pytest` on changes to `fitness-backend/` (job includes a Postgres service). All steps must pass before work is complete.
