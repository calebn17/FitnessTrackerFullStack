---
tags:
  - project
  - fitness
  - backend
  - implementation
  - planning
title: Fitness Platform - Backend Implementation Plans
created: 2026-04-25
status: draft
---

# Fitness Platform - Backend Implementation Plans

> Reference: [[Backend Design Spec]] | [[Fitness Platform - System Design]]

This document outlines phased implementation plans for building the Fitness Platform backend. Each phase is self-contained and results in a working, deployable increment.

---

## Phase Overview

### MVP Phases

| Phase | Name | Duration | Deliverable |
|-------|------|----------|-------------|
| 1 | Foundation | 1 week | Project scaffold, local dev, health endpoint |
| 2 | Database & Models | 1 week | Schema, migrations, repository layer |
| 3 | Auth Integration | 3-4 days | Supabase JWT validation, user sync |
| 4 | Workout CRUD | 1 week | Full workout API (create, read, update, delete) |
| 5 | Derived Metrics | 3-4 days | Automatic metrics calculation |
| 6 | Sync Protocol | 1 week | Offline sync endpoint |
| 7 | Observability | 3-4 days | Logging, metrics, Grafana integration |
| 8 | Production Hardening | 1 week | Rate limiting, security, performance |
| 9 | Deploy | 2-3 days | Render deployment, CI/CD |

**MVP estimated time: 6-7 weeks**

### Fast Follow Phases

| Phase | Name | Duration | Deliverable |
|-------|------|----------|-------------|
| 10 | Redis & Background Jobs | 2-3 days | ARQ worker infrastructure |
| 11 | AI Pipeline | 1.5 weeks | Claude integration, insight generation |

**Fast follow estimated time: 2 weeks**

---

## Phase 1: Foundation

**Goal:** Project scaffold with local development environment and a deployable health endpoint.

### Tasks

- [ ] **1.1 Project Initialization**
  - Create `fitness-backend/` repository
  - Initialize with `pyproject.toml` (using `uv` or `poetry`)
  - Configure `ruff` for linting, `mypy` for type checking
  - Add `.gitignore`, `README.md`

- [ ] **1.2 FastAPI App Scaffold**
  - Create `app/main.py` with FastAPI app
  - Add `/health` endpoint returning `{"status": "ok"}`
  - Create `app/config.py` with Pydantic Settings

- [ ] **1.3 Project Structure**
  - Create directory structure per [[Backend Design Spec#2. Project Structure]]
  - Add `__init__.py` files
  - Create placeholder modules

- [ ] **1.4 Local Development**
  - Create `docker-compose.yml` with:
    - PostgreSQL 15
    - Redis
  - Create `.env.example`
  - Add `Makefile` with common commands (`make dev`, `make test`, etc.)

- [ ] **1.5 Basic CI**
  - Create `.github/workflows/ci.yml`
  - Run linting and type checking on PR
  - Run tests (placeholder for now)

### Acceptance Criteria

```bash
# All pass:
make dev          # Starts local stack
curl localhost:8000/health  # Returns {"status": "ok"}
make lint         # No errors
make typecheck    # No errors
```

### Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
    "httpx>=0.27",
]
```

---

## Phase 2: Database & Models

**Goal:** Database schema with migrations and repository pattern.

### Tasks

- [ ] **2.1 SQLAlchemy Setup**
  - Add async SQLAlchemy dependencies
  - Create `app/core/database.py` with engine, session factory
  - Create `Base` declarative base

- [ ] **2.2 Alembic Setup**
  - Initialize Alembic (`alembic init alembic`)
  - Configure for async in `alembic/env.py`
  - Create initial migration

- [ ] **2.3 User Model**
  - Create `app/domains/users/models.py`
  - Fields: `id`, `supabase_id`, `email`, `created_at`, `updated_at`
  - Generate migration

- [ ] **2.4 Workout Models**
  - Create `app/domains/workouts/models.py`
  - Models: `Workout`, `ExerciseSet`, `DerivedMetrics`
  - Relationships and foreign keys
  - Generate migration

- [ ] **2.5 AI Models**
  - Create `app/domains/ai/models.py`
  - Model: `Insight`
  - Generate migration

- [ ] **2.6 Repository Pattern**
  - Create base repository class with common methods
  - Implement `UserRepository`, `WorkoutRepository`
  - Write unit tests for repositories

### Acceptance Criteria

```bash
make migrate              # Runs all migrations
make db-reset             # Drops and recreates schema
pytest tests/unit/test_repositories.py  # Passes
```

### Database Schema (Final State)

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supabase_id VARCHAR NOT NULL UNIQUE,
    email VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Workouts table
CREATE TABLE workouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    client_id UUID UNIQUE,
    date DATE NOT NULL,
    workout_type VARCHAR NOT NULL,
    notes TEXT,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Exercise sets table
CREATE TABLE exercise_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id UUID NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_name VARCHAR NOT NULL,
    set_number INTEGER NOT NULL,
    reps INTEGER NOT NULL,
    weight FLOAT,
    weight_unit VARCHAR DEFAULT 'lbs',
    rpe FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Derived metrics table
CREATE TABLE derived_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id UUID NOT NULL UNIQUE REFERENCES workouts(id) ON DELETE CASCADE,
    total_volume FLOAT,
    total_sets INTEGER,
    total_reps INTEGER,
    avg_rpe FLOAT,
    exercise_count INTEGER,
    muscle_groups TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insights table
CREATE TABLE insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id UUID NOT NULL UNIQUE REFERENCES workouts(id) ON DELETE CASCADE,
    ai_output JSONB NOT NULL,
    prompt_version VARCHAR,
    model_version VARCHAR,
    evaluation_score FLOAT,
    processing_time_ms INTEGER,
    status VARCHAR DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_workouts_user_id ON workouts(user_id);
CREATE INDEX idx_workouts_date ON workouts(date);
CREATE INDEX idx_workouts_client_id ON workouts(client_id);
CREATE INDEX idx_exercise_sets_workout_id ON exercise_sets(workout_id);
```

---

## Phase 3: Auth Integration

**Goal:** Validate Supabase JWTs and sync user data to local database.

### Tasks

- [ ] **3.1 Supabase Project Setup**
  - Create Supabase project
  - Enable Apple Sign-In and Google providers
  - Get JWT secret for validation

- [ ] **3.2 JWT Validation**
  - Install `PyJWT`
  - Create `app/core/security.py`
  - Implement `get_current_user` dependency
  - Validate audience, expiration, signature

- [ ] **3.3 User Sync Service**
  - Create `app/domains/users/service.py`
  - Implement `get_or_create_from_supabase()`
  - On first API call, create local user record

- [ ] **3.4 Users Router**
  - Create `app/domains/users/router.py`
  - `GET /api/v1/users/me` — returns current user
  - `PUT /api/v1/users/me` — update profile (placeholder)

- [ ] **3.5 Integration Tests**
  - Test valid JWT → user returned
  - Test expired JWT → 401
  - Test invalid JWT → 401
  - Test first-time user creation

### Acceptance Criteria

```bash
# With valid Supabase JWT:
curl -H "Authorization: Bearer $JWT" localhost:8000/api/v1/users/me
# Returns: {"id": "...", "email": "user@example.com"}

# With expired JWT:
# Returns: 401 {"error": {"code": "token_expired", ...}}
```

### Environment Variables

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_JWT_SECRET=your-jwt-secret
```

---

## Phase 4: Workout CRUD

**Goal:** Full CRUD API for workouts and exercise sets.

### Tasks

- [ ] **4.1 Pydantic Schemas**
  - Create `app/domains/workouts/schemas.py`
  - Request models: `WorkoutCreate`, `WorkoutUpdate`, `ExerciseSetCreate`
  - Response models: `WorkoutRead`, `ExerciseSetRead`
  - List/pagination params: `WorkoutListParams`

- [ ] **4.2 Workout Repository**
  - Implement `WorkoutRepository` methods:
    - `create(workout, db)` → `Workout`
    - `get_by_id(id, user_id, db)` → `Workout | None`
    - `list(user_id, params, db)` → `list[Workout], total`
    - `update(id, data, db)` → `Workout`
    - `soft_delete(id, db)` → `bool`

- [ ] **4.3 Workout Service**
  - Create `app/domains/workouts/service.py`
  - Validate user owns workout
  - Handle nested set creation
  - (Placeholder for metrics trigger)

- [ ] **4.4 Workout Router**
  - Create `app/domains/workouts/router.py`
  - Implement all endpoints per [[Backend Design Spec#5.2 Endpoint Specifications]]

- [ ] **4.5 Exercise Set Endpoints**
  - `POST /workouts/{id}/sets` — add set
  - `PUT /workouts/{id}/sets/{set_id}` — update set
  - `DELETE /workouts/{id}/sets/{set_id}` — delete set

- [ ] **4.6 Integration Tests**
  - Test CRUD lifecycle
  - Test pagination
  - Test user isolation (can't access other users' workouts)

### Acceptance Criteria

```bash
# Create workout
curl -X POST localhost:8000/api/v1/workouts \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "550e8400-e29b-41d4-a716-446655440000",
    "date": "2026-04-25",
    "workout_type": "strength",
    "sets": [
      {"exercise_name": "Squat", "set_number": 1, "reps": 5, "weight": 225}
    ]
  }'

# List workouts
curl localhost:8000/api/v1/workouts?page=1&per_page=10 \
  -H "Authorization: Bearer $JWT"

# Get single workout
curl localhost:8000/api/v1/workouts/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $JWT"
```

---

## Phase 5: Derived Metrics

**Goal:** Automatically calculate and store workout metrics after save.

### Tasks

- [ ] **5.1 Metrics Calculation**
  - Create `app/domains/workouts/metrics.py`
  - `calculate_metrics(workout: Workout) → DerivedMetrics`
  - Total volume: `sum(weight * reps)`
  - Total sets, reps, avg RPE
  - Exercise count, muscle groups

- [ ] **5.2 Muscle Group Mapping**
  - Create exercise → muscle group mapping
  - Start with common exercises (bench, squat, deadlift, etc.)
  - Handle unknown exercises gracefully

- [ ] **5.3 Integration with Workout Service**
  - After workout create/update, calculate metrics
  - Store in `derived_metrics` table
  - Include metrics in workout response

- [ ] **5.4 Unit Tests**
  - Test volume calculation
  - Test edge cases (bodyweight exercises, no RPE)
  - Test muscle group inference

### Acceptance Criteria

```json
// GET /api/v1/workouts/{id} includes:
{
  "metrics": {
    "total_volume": 4500,
    "total_sets": 12,
    "total_reps": 60,
    "avg_rpe": 7.5,
    "exercise_count": 4,
    "muscle_groups": ["chest", "triceps", "shoulders"]
  }
}
```

### Exercise → Muscle Group Mapping (Initial)

```python
EXERCISE_MUSCLE_MAP = {
    "bench press": ["chest", "triceps", "shoulders"],
    "squat": ["quadriceps", "glutes", "hamstrings"],
    "deadlift": ["back", "hamstrings", "glutes"],
    "overhead press": ["shoulders", "triceps"],
    "barbell row": ["back", "biceps"],
    "pull-up": ["back", "biceps"],
    "lat pulldown": ["back", "biceps"],
    "leg press": ["quadriceps", "glutes"],
    "leg curl": ["hamstrings"],
    "leg extension": ["quadriceps"],
    "bicep curl": ["biceps"],
    "tricep pushdown": ["triceps"],
    "lateral raise": ["shoulders"],
    "face pull": ["rear delts", "upper back"],
    # ... extend as needed
}
```

---

## Phase 6: Sync Protocol

**Goal:** Batch sync endpoint for offline-first mobile clients.

### Tasks

- [ ] **6.1 Sync Schemas**
  - Create `app/domains/sync/schemas.py`
  - `SyncChange`, `SyncRequest`, `SyncResponse`
  - `SyncConflict`, `ServerChange`

- [ ] **6.2 Sync Service**
  - Create `app/domains/sync/service.py`
  - Process each change in order
  - Detect conflicts (server timestamp > client timestamp)
  - Apply creates, updates, deletes
  - Fetch server changes since `last_sync_at`

- [ ] **6.3 Deduplication**
  - Use `client_id` to detect duplicate creates
  - If workout with `client_id` exists, skip or merge

- [ ] **6.4 Sync Router**
  - `POST /api/v1/sync` — process sync request
  - `GET /api/v1/sync/status` — return last sync timestamp

- [ ] **6.5 Integration Tests**
  - Test create sync
  - Test update sync with no conflict
  - Test update sync with conflict (server wins)
  - Test delete sync
  - Test server changes returned

### Acceptance Criteria

```bash
# Sync request
curl -X POST localhost:8000/api/v1/sync \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "last_sync_at": "2026-04-24T10:00:00Z",
    "changes": [
      {
        "operation": "create",
        "entity": "workout",
        "client_id": "...",
        "client_timestamp": "2026-04-25T15:30:00Z",
        "data": {...}
      }
    ]
  }'

# Response
{
  "sync_timestamp": "2026-04-25T15:35:00Z",
  "applied": ["client-id-1"],
  "conflicts": [],
  "server_changes": [...]
}
```

---

## Phase 7: Observability

**Goal:** Structured logging, metrics, and Grafana Cloud integration.

### Tasks

- [ ] **7.1 Structured Logging**
  - Install `structlog`
  - Create `app/core/logging.py`
  - Configure JSON output
  - Add request ID to all logs

- [ ] **7.2 Request Logging Middleware**
  - Log method, path, status, duration for every request
  - Include user_id if authenticated

- [ ] **7.3 Prometheus Metrics**
  - Install `prometheus-client`
  - Create `app/core/metrics.py`
  - Define metrics: request count, latency histogram

- [ ] **7.4 Metrics Endpoint**
  - `GET /metrics` — Prometheus scrape endpoint

- [ ] **7.5 Grafana Cloud Setup**
  - Create Grafana Cloud account
  - Configure Loki for log ingestion
  - Configure Prometheus remote write
  - Import or create dashboards

- [ ] **7.6 Health Check Enhancement**
  - Check database connectivity
  - Return detailed health status

### Acceptance Criteria

```bash
# Metrics endpoint
curl localhost:8000/metrics
# Returns Prometheus format metrics

# Logs are structured JSON
{"timestamp": "...", "level": "info", "event": "http.request", ...}

# Grafana dashboards show:
# - Request rate by endpoint
# - Latency p50/p95/p99
# - Error rate
```

---

## Phase 8: Production Hardening

**Goal:** Security, rate limiting, and performance optimizations.

### Tasks

- [ ] **8.1 Rate Limiting**
  - Install `slowapi`
  - Configure limits per endpoint
  - 100 req/min for reads, 20 req/min for writes

- [ ] **8.2 CORS Configuration**
  - Allow only known origins
  - Configure for iOS app and web app domains

- [ ] **8.3 Input Validation Hardening**
  - Review all Pydantic models
  - Add string length limits
  - Add numeric bounds

- [ ] **8.4 SQL Injection Review**
  - Verify all queries use parameterization
  - No raw SQL with string interpolation

- [ ] **8.5 Error Response Sanitization**
  - Don't leak stack traces in production
  - Generic error messages for 500s

- [ ] **8.6 Connection Pooling**
  - Configure pool size for expected load
  - Add connection timeout

- [ ] **8.7 Query Optimization**
  - Add indexes for common queries
  - Use EXPLAIN ANALYZE on slow queries
  - Implement eager loading where needed

- [ ] **8.8 Load Testing**
  - Use `locust` or `k6`
  - Test common flows under load
  - Identify bottlenecks

### Acceptance Criteria

```bash
# Rate limiting works
for i in {1..150}; do curl localhost:8000/api/v1/workouts; done
# Returns 429 after limit exceeded

# Load test passes
k6 run load_test.js
# p99 latency < 500ms at 50 concurrent users

# Security headers present
curl -I localhost:8000/api/v1/workouts
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
```

---

## Phase 9: Deploy

**Goal:** Production deployment on Render with CI/CD.

### Tasks

- [ ] **9.1 Dockerfile**
  - Multi-stage build for smaller image
  - Run as non-root user
  - Include migration step

- [ ] **9.2 Render Configuration**
  - Create `render.yaml`
  - Configure web service and database
  - Set environment variables

- [ ] **9.3 CI/CD Pipeline**
  - Update `.github/workflows/ci.yml`
  - Run tests on PR
  - Deploy to staging on merge to `develop`
  - Deploy to production on merge to `main`

- [ ] **9.4 Database Migrations in CD**
  - Run migrations before new version starts
  - Handle migration failures gracefully

- [ ] **9.5 Secrets Management**
  - Configure secrets in Render dashboard
  - Never commit secrets to repo

- [ ] **9.6 Smoke Tests**
  - Hit health endpoint after deploy
  - Verify API responds correctly

- [ ] **9.7 Monitoring Alerts**
  - Set up Grafana alerts for:
    - Error rate > 5%
    - Latency p99 > 2s
    - Health check failures

### Acceptance Criteria

```bash
# Production URL responds
curl https://fitness-api.onrender.com/health
{"status": "ok", "database": "connected"}

# GitHub Actions deploy on merge
git push origin main
# Triggers: test → build → deploy → smoke test

# Alerts configured
# Grafana shows active alerts for error rate and latency
```

### CI/CD Workflow

```yaml
# .github/workflows/ci.yml
name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install uv && uv sync
      - run: uv run ruff check .
      - run: uv run mypy app
      - run: uv run pytest

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: renderinc/render-action@v0.0.8
        with:
          token: ${{ secrets.RENDER_API_KEY }}
          service-id: ${{ secrets.RENDER_STAGING_SERVICE_ID }}

  deploy-production:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: renderinc/render-action@v0.0.8
        with:
          token: ${{ secrets.RENDER_API_KEY }}
          service-id: ${{ secrets.RENDER_PROD_SERVICE_ID }}
```

---

---

# Fast Follow Phases

---

## Phase 10: Redis & Background Jobs

**Goal:** Add Redis and ARQ worker infrastructure to support async processing.

**Prerequisite:** MVP deployed (Phase 9 complete)

### Tasks

- [ ] **10.1 Redis Setup**
  - Add Redis to `docker-compose.yml`
  - Add `redis` and `arq` dependencies
  - Create Redis connection in `app/core/redis.py`

- [ ] **10.2 ARQ Worker**
  - Create `app/workers/settings.py`
  - Create `app/workers/tasks.py`
  - Create `Dockerfile.worker`

- [ ] **10.3 Worker Deployment**
  - Add worker service to `render.yaml`
  - Configure Redis on Render
  - Test job enqueue/dequeue

### Acceptance Criteria

```bash
# Worker starts and connects to Redis
make worker        # Starts ARQ worker
# Enqueue a test job → worker picks it up
```

---

## Phase 11: AI Pipeline

**Goal:** Generate workout insights using Claude API with quality evaluation.

**Prerequisite:** Phase 10 (Redis + worker) complete

### Tasks

- [ ] **11.1 Insight Model & Migration**
  - Create `app/domains/ai/models.py` (Insight table)
  - Generate and run migration

- [ ] **11.2 Feature Extraction**
  - Create `app/domains/ai/pipeline.py`
  - Implement `extract_features(workout, history)`
  - Calculate volume trend vs recent workouts

- [ ] **11.3 Prompt Engineering**
  - Create `app/domains/ai/prompts.py`
  - Design structured output prompt
  - Define JSON schema for response

- [ ] **11.4 Claude Integration**
  - Install `anthropic` SDK
  - Create `app/domains/ai/service.py`
  - Implement `analyze_workout()`
  - Parse and validate JSON response

- [ ] **11.5 Evaluation Harness**
  - Create `app/domains/ai/evaluation.py`
  - Score output quality (0-1)
  - Check required fields, reasonable lengths

- [ ] **11.6 Background Job**
  - Add `process_workout_insight` task to ARQ worker
  - Handle success and failure states
  - Store status in `insights` table

- [ ] **11.7 Trigger from Workout Save**
  - After workout create, enqueue AI job
  - Store initial `Insight` with status "pending"

- [ ] **11.8 Insights Router**
  - `GET /api/v1/insights/workout/{id}` — get insight
  - `POST /api/v1/insights/workout/{id}/regenerate` — re-run

- [ ] **11.9 Tests**
  - Unit test feature extraction
  - Unit test evaluation scoring
  - Integration test with mocked Claude

### Acceptance Criteria

```bash
# Create workout → insight queued
# After worker processes:
curl localhost:8000/api/v1/insights/workout/{id}
{
  "status": "completed",
  "ai_output": {
    "summary": "Great upper body session...",
    "positives": ["Progressive overload on bench"],
    "suggestion": "Consider adding rear delt work",
    "recovery": "48 hours before next push day"
  },
  "evaluation_score": 0.95,
  "processing_time_ms": 1200
}
```

### Prompt Template (v1.0.0)

```
You are a fitness coach analyzing a workout log.

## Workout Data
- Date: {date}
- Type: {workout_type}
- Exercises: {exercises}
- Total Volume: {total_volume} lbs
- Sets: {total_sets} | Reps: {total_reps}
- Average RPE: {avg_rpe}
- Muscle Groups: {muscle_groups}
- Volume vs Last Similar Workout: {volume_trend}

## Instructions
Provide a brief, actionable analysis. Respond in JSON:

{
  "summary": "1-2 sentence overview",
  "positives": ["what went well"],
  "suggestion": "one specific improvement",
  "recovery": "recovery recommendation"
}
```

---

## Dependency Summary

```toml
# pyproject.toml
[project]
name = "fitness-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Web framework
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    
    # Database
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    
    # Auth
    "pyjwt>=2.8",
    
    # Observability
    "structlog>=24.1",
    "prometheus-client>=0.20",
    
    # Security
    "slowapi>=0.1",
    
    # Utilities
    "httpx>=0.27",
]

[project.optional-dependencies]
ai = [
    # Fast follow — add when implementing AI pipeline
    "arq>=0.25",
    "redis>=5.0",
    "anthropic>=0.18",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "mypy>=1.8",
    "factory-boy>=3.3",
    "faker>=24.0",
]
```

---

## Risk Mitigation

### MVP Risks

| Risk | Mitigation |
|------|------------|
| Supabase JWT changes | Pin JWT library, test auth on every deploy |
| Database connection exhaustion | Connection pooling, health checks |
| Slow sync for large batches | Pagination, background processing for large syncs |

### Fast Follow Risks

| Risk | Mitigation |
|------|------------|
| Claude API downtime | Graceful degradation, retry logic, status "pending" |
| Prompt drift | Version prompts, log all inputs/outputs |

---

## Success Metrics

### MVP

| Metric | Target |
|--------|--------|
| API latency p99 | < 500ms |
| Error rate | < 1% |
| Sync conflict rate | < 5% |
| Deployment frequency | Multiple times per week |
| Time to recover from failure | < 15 minutes |

### Fast Follow

| Metric | Target |
|--------|--------|
| AI insight quality score | > 0.8 average |
| AI pipeline processing time p95 | < 5s |
| Worker job failure rate | < 2% |
