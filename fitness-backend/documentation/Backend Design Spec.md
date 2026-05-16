---
tags:
  - project
  - fitness
  - backend
  - fastapi
  - python
  - architecture
title: Fitness Platform - Backend Design Spec
created: 2026-04-25
status: draft
---

# Fitness Platform - Backend Design Spec

> Reference: [[Fitness Platform - System Design]]

## 1. Overview

This document specifies the backend implementation for the Fitness Platform. The backend is a **FastAPI modular monolith** with clear domain boundaries, designed for eventual decomposition if needed.

### 1.1 How to read this spec

- Sections describing currently shipped behavior (for example users auth/profile, DB wiring, and test fixtures) are intended to match the repository implementation.
- Many larger code blocks in sync/AI/observability/deployment sections are **illustrative architecture examples** for planned phases, not copy-paste source.
- When a snippet and repository differ, source-of-truth is the code under `app/`, `alembic/`, and `tests/`, plus stack runbooks in `fitness-backend/README.md` and `fitness-backend/documentation/CLAUDE.md`.

### Key Decisions

| Aspect | Decision |
|--------|----------|
| **Framework** | FastAPI with Pydantic v2 |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Database** | PostgreSQL (Neon serverless) |
| **Auth** | Supabase Auth (JWT validation) |
| **Background Jobs** | Redis + ARQ (fast follow — not needed for MVP) |
| **LLM** | Anthropic Claude API (fast follow) |

---

## 2. Project Structure

```
fitness-backend/
├── alembic/                    # Database migrations
│   ├── versions/
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entrypoint
│   ├── config.py               # Settings and environment config
│   ├── dependencies.py         # FastAPI dependency injection
│   │
│   ├── core/                   # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── database.py         # Async SQLAlchemy engine/session
│   │   ├── exceptions.py       # Custom exception classes
│   │   ├── middleware.py       # Logging, timing, error handling
│   │   ├── security.py         # JWT validation, Supabase auth
│   │   └── logging.py          # Structured logging setup
│   │
│   ├── domains/                # Business domains
│   │   ├── __init__.py
│   │   │
│   │   ├── users/              # User domain
│   │   │   ├── __init__.py
│   │   │   ├── models.py       # SQLAlchemy models
│   │   │   ├── schemas.py      # Pydantic schemas
│   │   │   ├── service.py      # Business logic
│   │   │   ├── repository.py   # Data access layer
│   │   │   └── router.py       # API endpoints
│   │   │
│   │   ├── workouts/           # Workout domain
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── router.py
│   │   │   └── metrics.py      # Derived metrics calculation
│   │   │
│   │   ├── sync/               # Offline sync domain
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   │
│   │   └── ai/                 # AI insights domain (FAST FOLLOW)
│   │       ├── __init__.py
│   │       ├── models.py
│   │       ├── schemas.py
│   │       ├── service.py
│   │       ├── repository.py
│   │       ├── router.py
│   │       ├── pipeline.py     # AI processing pipeline
│   │       ├── prompts.py      # Claude prompt templates
│   │       └── evaluation.py   # Output quality scoring
│   │
│   └── workers/                # Background job workers (FAST FOLLOW)
│       ├── __init__.py
│       ├── settings.py         # ARQ worker settings
│       └── tasks.py            # Async job definitions
│
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── factories.py            # Test data factories
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   ├── seed_db.py              # Development data seeding
│   └── run_migrations.py
│
├── pyproject.toml              # Project dependencies
├── Dockerfile
├── docker-compose.yml          # Local development stack
├── render.yaml                 # Render deployment config
└── README.md
```

---

## 3. Domain Architecture

### 3.1 Layered Architecture (Per Domain)

Each domain follows a consistent layered pattern:

```
┌─────────────────────────────────────────────┐
│                  Router                      │  ← HTTP endpoints
│              (API layer)                     │
├─────────────────────────────────────────────┤
│                 Service                      │  ← Business logic
│           (Orchestration layer)              │
├─────────────────────────────────────────────┤
│               Repository                     │  ← Data access
│            (Persistence layer)               │
├─────────────────────────────────────────────┤
│                 Model                        │  ← SQLAlchemy ORM
│              (Data layer)                    │
└─────────────────────────────────────────────┘
```

### 3.2 Domain Responsibilities

#### Users Domain

| Component | Responsibility |
|-----------|----------------|
| `models.py` | `User` SQLAlchemy model |
| `schemas.py` | `SupabaseUserClaims`, `UserRead` |
| `repository.py` | `get_by_id`, `get_by_email`, `create`, `update` |
| `service.py` | `get_or_create_from_supabase` — sync Supabase user on first API call |
| `router.py` | `GET /users/me` — current user profile (Bearer JWT) |

#### Workouts Domain

| Component | Responsibility |
|-----------|----------------|
| `models.py` | `Workout`, `ExerciseSet`, `DerivedMetrics` |
| `schemas.py` | Request/response models for all CRUD operations |
| `repository.py` | All database queries with pagination, filtering |
| `service.py` | Validation, metrics calculation |
| `router.py` | Full REST API for workouts and sets |
| `metrics.py` | Volume/intensity calculation functions |

#### Sync Domain

| Component | Responsibility |
|-----------|----------------|
| `schemas.py` | `SyncRequest`, `SyncResponse`, `ChangeOperation` |
| `service.py` | Conflict detection, change application, response building |
| `router.py` | `POST /sync` — batch sync endpoint |

#### AI Domain (Fast Follow)

| Component | Responsibility |
|-----------|----------------|
| `models.py` | `Insight` |
| `schemas.py` | `InsightRead`, `InsightCreate`, `EvaluationResult` |
| `repository.py` | Insight storage and retrieval |
| `service.py` | Pipeline orchestration |
| `pipeline.py` | Feature extraction → Claude call → evaluation → storage |
| `prompts.py` | Prompt templates with structured output schemas |
| `evaluation.py` | Quality scoring, safety checks |

---

## 4. Database Layer

### 4.1 Models

Implementation uses **SQLAlchemy 2.0** declarative style (`Mapped` / `mapped_column`) on `Base` from `app/core/database.py`. Primary keys and timestamps use PostgreSQL defaults (`gen_random_uuid()`, `now()`) via Alembic-aligned server defaults.

Canonical definitions:

| Entity | Module | Table | Notes |
|--------|--------|-------|--------|
| `User` | `app/domains/users/models.py` | `users` | `supabase_id`, `email` unique |
| `Workout` | `app/domains/workouts/models.py` | `workouts` | `user_id` FK → `users`; optional `client_id` (unique); `deleted_at` for soft-delete (Phase 4+) |
| `ExerciseSet` | same | `exercise_sets` | `workout_id` FK `ON DELETE CASCADE`; indexes per Phase 2 plan |
| `DerivedMetrics` | same | `derived_metrics` | One row per workout (`workout_id` unique); `muscle_groups` as `TEXT[]` |
| `Insight` | `app/domains/ai/models.py` | `insights` | `workout_id` unique; `ai_output` `JSONB`; `status` default `'pending'` |

Relationship attribute names in code: `User.workouts`, `Workout.user`, `Workout.exercise_sets`, `Workout.derived_metrics`, `Workout.insight`, `ExerciseSet.workout`, `DerivedMetrics.workout`, `Insight.workout`. Cascades match FK `ON DELETE CASCADE` where defined in migrations.

### 4.2 Database Connection

Core wiring lives in `app/core/database.py`: a **lazy singleton** async engine (`get_engine`), `async_sessionmaker` (`get_session_factory`), and `get_db_session` for FastAPI (yield session; **callers commit**). `dispose_engine()` runs on app shutdown; tests use `init_database_engine` / `reset_database_singletons` when overriding `DATABASE_URL`.

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
```

FastAPI can import `get_db_session` from `app.dependencies` (re-export) or `app.core.database`.

**Settings:** `database_url` from `app/config.py` (`DATABASE_URL` env; default matches Docker Compose).

**Local Docker mapping:** this backend publishes Postgres as host `5433` to container `5432` (`5433:5432`) so it can coexist with other local projects that already use host `5432`. Local default DSN is `postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness`.

**Migrations:** Alembic async env in `alembic/env.py`; revisions under `alembic/versions/phase2_0*.py`. Run `make migrate` from `fitness-backend/`.

---

## 5. API Layer

### 5.1 Router Structure

```python
# app/main.py (simplified; see repo for lifespan and /health)
from fastapi import FastAPI

from app.config import get_settings
from app.domains.users.router import router as users_router

def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)  # lifespan + /health in repo
    application.include_router(users_router, prefix=settings.api_v1_prefix)
    return application
```

Routers set their own path prefix inside the domain (for example `users` exposes `/users/me`, which becomes `/api/v1/users/me` once mounted with `settings.api_v1_prefix`, default `/api/v1`). Additional domain routers (`workouts`, `sync`, `ai`) are planned; not all are registered in the scaffold yet.

### 5.2 Endpoint Specifications

#### Users Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/v1/users/me` | Get current user profile; creates local `User` on first authenticated request and syncs email from token when changed | Required (Bearer JWT) |

**`GET /api/v1/users/me` response (200)** — JSON body matches `UserRead`: `id` (UUID), `supabase_id`, `email`, `created_at`, `updated_at` (nullable). The access token must include string claims `sub`, `email`, `exp`, and `aud` (validated with PyJWT; audience defaults to settings `supabase_jwt_audience`, usually `authenticated`).

**Auth errors (401)** — JSON `detail` is an object with stable `code` values including: `missing_authorization`, `invalid_authorization_format`, `auth_not_configured`, `token_expired`, `token_invalid_audience`, `token_invalid_signature`, `token_missing_claim`, `token_invalid`.

**User claims (422)** — If the JWT decodes but cannot be turned into a local user (for example missing `email`), `detail` includes `code`: `invalid_user_claims` plus Pydantic `errors`.

#### Workouts Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/v1/workouts` | List workouts (paginated) | Required |
| `POST` | `/api/v1/workouts` | Create workout with sets | Required |
| `GET` | `/api/v1/workouts/{id}` | Get workout with sets and metrics | Required |
| `PUT` | `/api/v1/workouts/{id}` | Update workout | Required |
| `DELETE` | `/api/v1/workouts/{id}` | Soft delete workout | Required |
| `POST` | `/api/v1/workouts/{id}/sets` | Add set to workout | Required |
| `PUT` | `/api/v1/workouts/{id}/sets/{set_id}` | Update set | Required |
| `DELETE` | `/api/v1/workouts/{id}/sets/{set_id}` | Delete set | Required |

#### Sync Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/v1/sync` | Batch sync changes | Required |
| `GET` | `/api/v1/sync/status` | Get sync status/last sync time | Required |

#### AI Insights Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/v1/insights/workout/{workout_id}` | Get insight for workout | Required |
| `POST` | `/api/v1/insights/workout/{workout_id}/regenerate` | Regenerate insight | Required |

### 5.3 Request/Response Schemas (illustrative for planned domains)

```python
# app/domains/workouts/schemas.py
from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID

class ExerciseSetCreate(BaseModel):
    exercise_name: str = Field(..., min_length=1, max_length=100)
    set_number: int = Field(..., ge=1)
    reps: int = Field(..., ge=1, le=1000)
    weight: float | None = Field(None, ge=0)
    weight_unit: str = Field("lbs", pattern="^(lbs|kg)$")
    rpe: float | None = Field(None, ge=1, le=10)

class WorkoutCreate(BaseModel):
    client_id: UUID  # Client-generated UUID for deduplication
    date: date
    workout_type: str = Field(..., pattern="^(strength|cardio|flexibility|other)$")
    notes: str | None = Field(None, max_length=1000)
    sets: list[ExerciseSetCreate] = Field(default_factory=list)

class WorkoutRead(BaseModel):
    id: UUID
    client_id: UUID
    date: date
    workout_type: str
    notes: str | None
    sets: list[ExerciseSetRead]
    metrics: DerivedMetricsRead | None
    insight_status: str | None  # "pending", "completed", "failed", None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class WorkoutListParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    workout_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    order_by: str = Field("date", pattern="^(date|created_at)$")
    order_dir: str = Field("desc", pattern="^(asc|desc)$")
```

---

## 6. Sync Protocol (illustrative, planned)

### 6.1 Sync Request Format

```python
# app/domains/sync/schemas.py
from enum import Enum

class OperationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class EntityType(str, Enum):
    WORKOUT = "workout"
    EXERCISE_SET = "exercise_set"

class SyncChange(BaseModel):
    operation: OperationType
    entity: EntityType
    client_id: UUID  # Client-side UUID
    client_timestamp: datetime
    data: dict  # Entity data for create/update, empty for delete

class SyncRequest(BaseModel):
    last_sync_at: datetime | None  # None for first sync
    changes: list[SyncChange]

class SyncResponse(BaseModel):
    sync_timestamp: datetime  # Use this as next last_sync_at
    applied: list[UUID]  # client_ids that were successfully applied
    conflicts: list[SyncConflict]  # Changes that had conflicts
    server_changes: list[ServerChange]  # Changes from server since last_sync_at
```

### 6.2 Conflict Resolution

```python
# app/domains/sync/service.py
class SyncService:
    async def process_sync(
        self,
        user_id: UUID,
        request: SyncRequest,
        db: AsyncSession
    ) -> SyncResponse:
        applied = []
        conflicts = []
        
        for change in request.changes:
            # Check for existing entity by client_id
            existing = await self._get_by_client_id(change.entity, change.client_id, db)
            
            if change.operation == OperationType.CREATE:
                if existing:
                    # Already exists — deduplicate (no-op or conflict)
                    if existing.updated_at > change.client_timestamp:
                        conflicts.append(SyncConflict(
                            client_id=change.client_id,
                            server_version=self._serialize(existing),
                            resolution="server_wins"
                        ))
                    else:
                        applied.append(change.client_id)  # Already synced
                else:
                    await self._create(change, user_id, db)
                    applied.append(change.client_id)
                    
            elif change.operation == OperationType.UPDATE:
                if existing and existing.updated_at > change.client_timestamp:
                    conflicts.append(...)
                else:
                    await self._update(change, db)
                    applied.append(change.client_id)
                    
            elif change.operation == OperationType.DELETE:
                await self._soft_delete(change, db)
                applied.append(change.client_id)
        
        # Fetch server changes since last sync
        server_changes = await self._get_changes_since(
            user_id, request.last_sync_at, db
        )
        
        return SyncResponse(
            sync_timestamp=datetime.now(UTC),
            applied=applied,
            conflicts=conflicts,
            server_changes=server_changes
        )
```

---

## 7. AI Pipeline (Fast Follow, illustrative)

### 7.1 Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          AI Pipeline                                      │
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌───────────┐ │
│  │   Trigger   │───▶│  Feature    │───▶│   Claude    │───▶│ Evaluate  │ │
│  │ (on save)   │    │ Extraction  │    │   API       │    │ & Store   │ │
│  └─────────────┘    └─────────────┘    └─────────────┘    └───────────┘ │
│        │                                                                  │
│        │ Async (via ARQ)                                                 │
│        ▼                                                                  │
│  ┌─────────────┐                                                         │
│  │   Redis     │                                                         │
│  │   Queue     │                                                         │
│  └─────────────┘                                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Feature Extraction

```python
# app/domains/ai/pipeline.py
from dataclasses import dataclass

@dataclass
class WorkoutFeatures:
    total_volume: float
    total_sets: int
    total_reps: int
    avg_rpe: float | None
    exercise_count: int
    unique_exercises: list[str]
    muscle_groups: list[str]
    workout_type: str
    duration_category: str  # "quick", "standard", "extended"
    volume_trend: str | None  # vs last similar workout: "up", "down", "same"

def extract_features(workout: Workout, history: list[Workout]) -> WorkoutFeatures:
    """Extract structured features for LLM context."""
    sets = workout.sets
    
    total_volume = sum(s.weight * s.reps for s in sets if s.weight)
    muscle_groups = infer_muscle_groups([s.exercise_name for s in sets])
    
    # Compare to recent similar workouts
    similar = [w for w in history if w.workout_type == workout.workout_type]
    volume_trend = None
    if similar:
        last_volume = similar[0].metrics.total_volume if similar[0].metrics else 0
        if total_volume > last_volume * 1.05:
            volume_trend = "up"
        elif total_volume < last_volume * 0.95:
            volume_trend = "down"
        else:
            volume_trend = "same"
    
    return WorkoutFeatures(
        total_volume=total_volume,
        total_sets=len(sets),
        total_reps=sum(s.reps for s in sets),
        avg_rpe=mean([s.rpe for s in sets if s.rpe]) if any(s.rpe for s in sets) else None,
        exercise_count=len(set(s.exercise_name for s in sets)),
        unique_exercises=list(set(s.exercise_name for s in sets)),
        muscle_groups=muscle_groups,
        workout_type=workout.workout_type,
        duration_category=categorize_duration(len(sets)),
        volume_trend=volume_trend,
    )
```

### 7.3 Claude Prompts

```python
# app/domains/ai/prompts.py
WORKOUT_ANALYSIS_PROMPT = """
You are a fitness coach analyzing a workout log. Provide helpful, actionable insights.

## Workout Data
- Date: {date}
- Type: {workout_type}
- Total Volume: {total_volume} lbs
- Sets: {total_sets}
- Reps: {total_reps}
- Exercises: {exercises}
- Muscle Groups: {muscle_groups}
- Average RPE: {avg_rpe}
- Volume vs Last Similar Workout: {volume_trend}

## Instructions
Analyze this workout and provide:
1. A brief summary (1-2 sentences)
2. What went well
3. One specific, actionable suggestion for improvement
4. Recovery recommendation

Respond in JSON format:
{{
    "summary": "string",
    "positives": ["string"],
    "suggestion": "string", 
    "recovery": "string"
}}
"""

PROMPT_VERSION = "v1.0.0"
```

### 7.4 Claude API Integration

```python
# app/domains/ai/service.py
import anthropic
from app.config import settings

class AIService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
    
    async def analyze_workout(
        self,
        workout: Workout,
        features: WorkoutFeatures
    ) -> InsightCreate:
        prompt = WORKOUT_ANALYSIS_PROMPT.format(
            date=workout.date,
            workout_type=workout.workout_type,
            total_volume=features.total_volume,
            total_sets=features.total_sets,
            total_reps=features.total_reps,
            exercises=", ".join(features.unique_exercises),
            muscle_groups=", ".join(features.muscle_groups),
            avg_rpe=features.avg_rpe or "Not recorded",
            volume_trend=features.volume_trend or "First workout of this type",
        )
        
        start_time = time.time()
        
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Parse and validate JSON response
        ai_output = self._parse_response(response.content[0].text)
        
        # Evaluate quality
        score = self._evaluate_output(ai_output, features)
        
        return InsightCreate(
            workout_id=workout.id,
            ai_output=ai_output,
            prompt_version=PROMPT_VERSION,
            model_version=self.model,
            evaluation_score=score,
            processing_time_ms=processing_time_ms,
            status="completed",
        )
    
    def _evaluate_output(self, output: dict, features: WorkoutFeatures) -> float:
        """Score output quality 0-1."""
        score = 1.0
        
        # Check required fields
        required = ["summary", "positives", "suggestion", "recovery"]
        for field in required:
            if field not in output or not output[field]:
                score -= 0.25
        
        # Check summary length (not too short, not too long)
        summary = output.get("summary", "")
        if len(summary) < 20 or len(summary) > 300:
            score -= 0.1
        
        # Check that suggestion is actionable (contains a verb)
        # Basic heuristic — could be more sophisticated
        
        return max(0, score)
```

### 7.5 Background Worker

```python
# app/workers/tasks.py
from arq import create_pool
from arq.connections import RedisSettings
from app.domains.ai.service import AIService
from app.domains.ai.pipeline import extract_features
from app.domains.workouts.repository import WorkoutRepository

async def process_workout_insight(ctx, workout_id: str):
    """Background job to generate workout insight."""
    db = ctx["db"]
    ai_service = ctx["ai_service"]
    workout_repo = ctx["workout_repo"]
    insight_repo = ctx["insight_repo"]
    
    workout = await workout_repo.get_by_id(UUID(workout_id), db)
    if not workout:
        return {"status": "error", "message": "Workout not found"}
    
    # Get recent history for comparison
    history = await workout_repo.get_recent_by_user(
        workout.user_id, limit=10, db=db
    )
    
    # Extract features
    features = extract_features(workout, history)
    
    try:
        # Generate insight
        insight = await ai_service.analyze_workout(workout, features)
        await insight_repo.create(insight, db)
        return {"status": "completed", "workout_id": workout_id}
    except Exception as e:
        # Store failure
        await insight_repo.create(InsightCreate(
            workout_id=workout.id,
            ai_output={},
            status="failed",
            error_message=str(e),
        ), db)
        return {"status": "failed", "error": str(e)}

class WorkerSettings:
    functions = [process_workout_insight]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

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

## 12. Observability Integration

### 12.1 Structured Logging

```python
# app/core/logging.py
import structlog
from app.config import settings

def setup_logging():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

logger = structlog.get_logger()

# Usage in routes
@router.post("/workouts")
async def create_workout(workout: WorkoutCreate, user: User = Depends(get_current_user)):
    logger.info(
        "workout.create",
        user_id=str(user.id),
        workout_type=workout.workout_type,
        set_count=len(workout.sets),
    )
```

### 12.2 Metrics

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"]
)

AI_PIPELINE_DURATION = Histogram(
    "ai_pipeline_duration_seconds",
    "AI pipeline processing time",
    ["status"]
)

AI_EVALUATION_SCORE = Histogram(
    "ai_evaluation_score",
    "AI output quality score",
    buckets=[0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
)
```

---

## 13. Deployment

### 13.1 Render Configuration

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

### 13.2 Dockerfile

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
