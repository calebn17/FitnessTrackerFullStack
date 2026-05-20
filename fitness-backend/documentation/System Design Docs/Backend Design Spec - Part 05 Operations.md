---
tags: [project, fitness, backend, architecture]
title: Fitness Platform — Backend Design Spec (Part 5 — Authentication, configuration, errors, testing, observability, deployment)
parent: Backend Design Spec
created: 2026-04-25
status: draft
---

# Part 5 — Authentication, configuration, errors, testing, observability, deployment

**Parent:** [Backend Design Spec (index)](Backend%20Design%20Spec.md)

**In this part:** [§8 Authentication](#8-authentication) · [§9 Configuration](#9-configuration) · [§10 Error handling](#10-error-handling) · [§11 Testing](#11-testing-strategy) · [§12 Production hardening](#12-production-hardening-phase-8) · [§13 Observability](#13-observability-integration) · [§14 Deployment](#14-deployment) · [Next steps](#next-steps)

---

## 8. Authentication

**Phase 3 (implemented)** — The API validates Supabase-issued **HS256** access tokens from the `Authorization: Bearer <token>` header.

### 8.1 Module responsibilities

| Module | Role |
|--------|------|
| `app/config.py` | `Settings.supabase_jwt_secret`, `supabase_jwt_audience` (default `authenticated`), `supabase_url` (optional, reserved) |
| `app/core/security.py` | `decode_supabase_access_token()` (PyJWT `jwt.decode` with required `exp`, `sub`, `aud`); `get_supabase_jwt_claims` dependency parses Bearer, maps PyJWT failures to **401** with JSON `detail` `{ "code", "message", ... }` and `WWW-Authenticate: Bearer` |
| `app/dependencies.py` | Re-exports `get_db_session`, `get_settings`, `get_supabase_jwt_claims` for routers |
| `app/domains/users/service.py` | `UserService.get_or_create_from_supabase(claims)` — validates `sub` + `email` via `SupabaseUserClaims`, looks up `UserRepository.get_by_supabase_id`, syncs email when changed, else `create` + `commit` (with `IntegrityError` recovery for races and email uniqueness conflicts) |
| `app/domains/users/router.py` | `GET /users/me` mounted under `settings.api_v1_prefix`; depends on `get_supabase_jwt_claims` + `get_db_session`; returns `UserRead`; `ValidationError` from user provisioning → **422** `invalid_user_claims` |

### 8.2 Stable `401` `detail.code` values

`missing_authorization`, `invalid_authorization_format`, `auth_not_configured` (empty JWT secret), `token_expired`, `token_invalid_audience`, `token_invalid_signature`, `token_missing_claim` (includes `claim` key), `token_invalid`.

---

## 9. Configuration

The snippet below is conceptual; use `app/config.py` as source-of-truth for active settings/defaults.

```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    app_name: str = "Fitness Platform API"
    debug: bool = False
    environment: str = "development"
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str
    
    # Supabase (Phase 3 — JWT validation; source of truth: `app/config.py`)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    
    # Anthropic
    anthropic_api_key: str
    
    # Observability
    grafana_api_key: str | None = None
    
    # Feature flags
    ai_pipeline_enabled: bool = True
    ai_pipeline_async: bool = True  # False = inline processing
    
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

---

## 10. Error Handling

Illustrative application-level pattern for future domain expansion.

```python
# app/core/exceptions.py
from fastapi import HTTPException

class AppException(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, code: str = "app_error"):
        self.message = message
        self.code = code

class NotFoundError(AppException):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} with id {id} not found", "not_found")

class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(message, "conflict")

class ValidationError(AppException):
    def __init__(self, message: str):
        super().__init__(message, "validation_error")

# app/core/middleware.py
from fastapi import Request
from fastapi.responses import JSONResponse

async def exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=_get_status_code(exc),
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        }
    )

def _get_status_code(exc: AppException) -> int:
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, ValidationError):
        return 422
    return 500
```

---

## 11. Testing Strategy

### 11.1 Test Structure

Illustrative target structure as additional domains are implemented.

```
tests/
├── conftest.py              # Shared fixtures
├── factories.py             # Factory Boy factories
├── unit/
│   ├── test_metrics.py      # Derived metrics calculation
│   ├── test_features.py     # AI feature extraction
│   └── test_evaluation.py   # AI output evaluation
├── integration/
│   ├── test_workouts.py     # Workout CRUD with DB
│   ├── test_sync.py         # Sync endpoint tests
│   └── test_ai_pipeline.py  # AI pipeline tests (mocked Claude)
└── e2e/
    └── test_workout_flow.py # Full workout → insight flow
```

### 11.2 Key Fixtures (current backend)

```python
# tests/conftest.py (simplified)
@pytest.fixture(scope="session")
def migrated_database() -> None:
    # Runs `python -m alembic upgrade head` once per session.
    ...

@pytest.fixture
async def db_session(migrated_database) -> AsyncGenerator[AsyncSession, None]:
    # Initializes engine for configured DATABASE_URL (local default host port 5433),
    # truncates tables before each test, yields session, then rolls back and disposes engine.
    ...
```

```python
# tests/integration/test_users_router.py (simplified)
@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[TestClient, None]:
    # Ensures database setup fixture is active for this test and overrides app settings.
    # The app's get_db_session dependency is overridden to create request-loop-local
    # async SQLAlchemy sessions, preventing cross-event-loop asyncpg errors under TestClient.
    ...
```

---

## 12. Production hardening (Phase 8)

Shipped cross-cutting behavior in `app/main.py`, `app/core/rate_limit.py`, `app/core/security_headers.py`, `app/config.py`, and domain routers:

| Concern | Implementation |
|---------|------------------|
| **Rate limits** | SlowAPI per-IP read/write limits on `/api/v1/*` routes; `429` on exceed |
| **CORS** | `CORSMiddleware`; explicit `CORS_ALLOWED_ORIGINS` in production; dev/test localhost defaults when unset |
| **Security headers** | `nosniff`, `DENY` frame, `no-referrer`, `no-store` on `/api/v1` responses |
| **Sanitized 500s** | Generic `internal_server_error` when `debug=false` |
| **DB pool** | `create_async_engine(..., pool_size=..., max_overflow=..., pool_timeout=..., pool_recycle=...)` |
| **Indexes** | Alembic `phase2_04_workout_query_indexes` — `workouts(user_id, deleted_at, date)` and `workouts(user_id, client_id)` |
| **Load tests** | `fitness-backend/load-tests/common_flows.js` (k6) |

---

## 13. Observability Integration

**Shipped in Phase 7** (see `app/core/logging.py`, `app/core/middleware.py`, `app/core/metrics.py`, `app/main.py`):

| Concern | Behavior |
|---------|----------|
| **Logging** | `configure_logging(debug=settings.debug)` runs in `create_app()`. Logs are **JSON** lines to stdout with `timestamp` (ISO), `level`, `event`, and bound context (`request_id`, optional `user_id`). |
| **Request log** | `RequestObservabilityMiddleware` logs `http.request` with `method`, `path`, `route` (matched template when available), `status`, `duration_ms`. Propagates or sets **`X-Request-ID`** on the response. |
| **Auth context** | If `Authorization: Bearer` decodes with the configured Supabase secret/audience, **`user_id`** is set to JWT `sub` for logs (decode failures are ignored; routes still enforce auth). |
| **Metrics** | `http_requests_total` (labels `method`, `route`, `status_code`) and `http_request_duration_seconds` (labels `method`, `route`). **`GET /metrics`** is excluded from metric increments to avoid self-scrape noise. |
| **Health** | **`GET /health`** uses `Depends(get_db_session)`, runs `SELECT 1`, returns `{"status":"ok","checks":{"database":{"status":"ok"}}}` or **503** `{"status":"unhealthy",...}` on failure. |

Runtime dependencies: `structlog`, `prometheus-client` (see `pyproject.toml`).

### 13.1 Future metrics (AI pipeline)

Illustrative histograms for later phases (not registered until the AI pipeline ships):

```python
# Future: app/core/metrics.py additions
AI_PIPELINE_DURATION = Histogram(
    "ai_pipeline_duration_seconds",
    "AI pipeline processing time",
    ["status"],
)
```

### 13.2 Grafana Cloud (operator runbook)

1. Create a **Grafana Cloud** stack (Hosted Grafana + **Mimir** or **Prometheus** remote write + **Loki**).
2. **Metrics:** Configure a Grafana Agent or Prometheus scrape job against the service URL `https://<host>/metrics` (or internal URL). Import or build panels on `http_requests_total` and `http_request_duration_seconds` (rate, histogram_quantile for latency).
3. **Logs:** Ship container stdout (JSON) to **Loki** (Docker log driver, Grafana Agent `loki.source`, or platform log drain). Parse JSON; index on `request_id`, `level`, `event`.
4. **Alerts:** Start with error rate (5xx ratio from `status` / `status_code`) and health check failures from the load balancer or synthetic checks.

---

## 14. Deployment

### 14.1 Render Configuration

```yaml
# render.yaml
services:
  - type: web
    name: fitness-api
    runtime: docker
    dockerfilePath: ./Dockerfile
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: fitness-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: fitness-redis
          property: connectionString
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: SUPABASE_JWT_SECRET
        sync: false
    healthCheckPath: /health
    autoDeploy: true

  - type: worker
    name: fitness-worker
    runtime: docker
    dockerfilePath: ./Dockerfile.worker
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: fitness-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: fitness-redis
          property: connectionString

databases:
  - name: fitness-db
    plan: starter

redis:
  - name: fitness-redis
    plan: starter
```

### 14.2 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install .

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
```

---

## Next Steps

See [[Backend Implementation Plans]] for phased build-out.
