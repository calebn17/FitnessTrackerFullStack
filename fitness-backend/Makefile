.PHONY: dev down lint typecheck test migrate db-reset

# Run all commands from this directory: `cd fitness-backend`

dev:
	docker compose up -d
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

down:
	docker compose down

lint:
	ruff check .

typecheck:
	mypy app

test:
	PYTHONPATH=. pytest

migrate:
	alembic upgrade head

db-reset:
	docker compose exec -T postgres psql -U fitness -d fitness -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO fitness; GRANT ALL ON SCHEMA public TO public;"
	alembic upgrade head
