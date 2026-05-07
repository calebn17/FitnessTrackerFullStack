# Fitness Platform — Backend (Phase 1)

FastAPI service scaffold with local PostgreSQL + Redis via Docker Compose.

## Prerequisites

- Python 3.11+
- Docker / Docker Compose
- [`uv`](https://docs.astral.sh/uv/) or `pip` for dependencies (install locally; not run in agent harness)

## Setup

```bash
cd fitness-backend
cp .env.example .env
uv sync --extra dev
# or: pip install -e ".[dev]"
```

## Development

Start databases, then the API (from `fitness-backend/`):

```bash
make dev
```

- API: `http://localhost:8000`
- Health: `curl http://localhost:8000/health` → `{"status":"ok"}`

Stop containers:

```bash
make down
```

## Quality

```bash
make lint
make typecheck
make test
```

## Layout

See [Documentation/Backend Design Spec.md](../Documentation/Backend%20Design%20Spec.md) for the full modular monolith structure. Alembic is scaffolded under `alembic/`; migrations are added in Phase 2.

## CI

GitHub Actions workflow lives at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (repository root) and runs on changes under `fitness-backend/`.
