.PHONY: dev down lint typecheck test migrate db-reset

# Run all commands from this directory: `cd fitness-backend`

# Prefer project venv when present (so `make` works without manual `activate`)
PYTHON := $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

dev:
	docker compose up -d
	$(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

down:
	docker compose down

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy app

test:
	PYTHONPATH=. $(PYTHON) -m pytest

migrate:
	alembic upgrade head

db-reset:
	docker compose exec -T postgres psql -U fitness -d fitness -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO fitness; GRANT ALL ON SCHEMA public TO public;"
	alembic upgrade head
