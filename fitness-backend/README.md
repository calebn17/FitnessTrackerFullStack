# Fitness Platform — Backend

FastAPI modular monolith with PostgreSQL + Redis via Docker Compose; **Phase 2** delivers SQLAlchemy models, Alembic migrations, and repositories (see project plans).

## Prerequisites

- Python 3.11+
- Docker / Docker Compose
- [`uv`](https://docs.astral.sh/uv/) or `pip` for dependencies (install locally; not run in agent harness)

## Setup

```bash
cd fitness-backend
cp .env.example .env
```

**Dependencies (pick one)**

Using a local virtualenv (recommended with plain `pip`; `.venv/` is gitignored):

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Using [`uv`](https://docs.astral.sh/uv/) (creates/manages its own env by default):

```bash
uv sync --extra dev
```

Plain install without an explicit venv (not recommended):

```bash
pip install -e ".[dev]"
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

Activate `.venv` first (or use `uv run`) so `ruff`, `mypy`, and `pytest` come from that environment:

```bash
make lint
make typecheck
make test
```

Repository tests need Postgres running (`docker compose up -d postgres`), then:

```bash
PYTHONPATH=. pytest tests/unit/test_repositories.py
```

## Layout

See [documentation/Backend Design Spec.md](documentation/Backend%20Design%20Spec.md) for the full modular monolith structure. Alembic migrations live under `alembic/versions/` (`make migrate`, `make db-reset`).

## CI

GitHub Actions workflow lives at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (repository root) and runs on changes under `fitness-backend/`: `ruff` → `mypy` → `alembic upgrade head` → `pytest` (with a Postgres service).
