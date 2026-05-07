.PHONY: dev down lint typecheck test

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
