---
tags: [project, fitness, backend, architecture]
title: Fitness Platform — Backend Design Spec (Part 3 — API layer)
parent: Backend Design Spec
created: 2026-04-25
status: draft
---

# Part 3 — API layer

**Parent:** [Backend Design Spec (index)](Backend%20Design%20Spec.md)

**In this part:** [§5.1 Router structure](#51-router-structure) · [§5.2 Endpoints](#52-endpoint-specifications) · [§5.3 Schemas](#53-requestresponse-schemas-illustrative-for-planned-domains)

---

## 5. API Layer

### 5.1 Router Structure

```python
# app/main.py (simplified; see repo for lifespan and /health)
from fastapi import FastAPI

from app.config import get_settings
from app.domains.users.router import router as users_router
from app.domains.workouts.router import router as workouts_router

def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)  # lifespan + /health in repo
    application.include_router(users_router, prefix=settings.api_v1_prefix)
    application.include_router(workouts_router, prefix=settings.api_v1_prefix)
    return application
```

Routers set their own path prefix inside the domain (for example `users` exposes `/users/me`, which becomes `/api/v1/users/me` once mounted with `settings.api_v1_prefix`, default `/api/v1`). The `workouts` router is registered for Phase 4 CRUD; `sync` and `ai` routers remain planned/future wiring in `create_app`.

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

**Path `{id}`** — Server-assigned workout UUID (`workouts.id`), not the offline `client_id`.

**List response (200 `GET /api/v1/workouts`)** — JSON body: `items` (array of `WorkoutRead`), `total` (integer), `page`, `per_page`.

**List query validation (422)** — Invalid list query values (for example unsupported `order_by`, `order_dir`, or `workout_type`) return `422 Unprocessable Entity`.

**Update notes semantics** — In `PUT /api/v1/workouts/{id}`, sending `notes` as `null` explicitly clears stored notes. Omitting `notes` leaves notes unchanged.

**Soft delete** — `DELETE /api/v1/workouts/{id}` sets `workouts.deleted_at`; soft-deleted rows are omitted from list and single-get responses.

**Errors** — `404` with `detail.code` `workout_not_found` or `set_not_found` when the resource is missing or not owned by the caller. `409` with `detail.code` `duplicate_client_id` when `client_id` collides with an existing workout (global unique on `workouts.client_id`).

**Derived metrics (Phase 5)** — Every `WorkoutRead` includes a `metrics` object (not null): totals are recomputed and upserted into `derived_metrics` on create and whenever sets change (`PUT` with `sets`, `POST/PUT/DELETE` set routes). Replacing all sets with `[]` yields zeroed metrics. Pure metadata updates (`PUT` without `sets`) leave metrics unchanged.

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
# app/domains/workouts/schemas.py (representative; see repo for full models)
from pydantic import BaseModel, ConfigDict, Field
from datetime import date, datetime
from uuid import UUID

class ExerciseSetCreate(BaseModel):
    exercise_name: str = Field(..., min_length=1, max_length=100)
    set_number: int = Field(..., ge=1)
    reps: int = Field(..., ge=1, le=1000)
    weight: float | None = Field(None, ge=0)
    weight_unit: str = Field("lbs", pattern="^(lbs|kg)$")
    rpe: float | None = Field(None, ge=1, le=10)

class ExerciseSetUpdate(BaseModel):
    exercise_name: str | None = Field(None, min_length=1, max_length=100)
    set_number: int | None = Field(None, ge=1)
    reps: int | None = Field(None, ge=1, le=1000)
    weight: float | None = Field(None, ge=0)
    weight_unit: str | None = Field(None, pattern="^(lbs|kg)$")
    rpe: float | None = Field(None, ge=1, le=10)

class ExerciseSetRead(BaseModel):
    id: UUID
    exercise_name: str
    set_number: int
    reps: int
    weight: float | None
    weight_unit: str
    rpe: float | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class DerivedMetricsRead(BaseModel):
    id: UUID
    total_volume: float | None
    total_sets: int | None
    total_reps: int | None
    avg_rpe: float | None
    exercise_count: int | None
    muscle_groups: list[str] | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class WorkoutCreate(BaseModel):
    client_id: UUID  # Client-generated UUID for deduplication
    date: date
    workout_type: str = Field(..., pattern="^(strength|cardio|flexibility|other)$")
    notes: str | None = Field(None, max_length=1000)
    sets: list[ExerciseSetCreate] = Field(default_factory=list)

class WorkoutUpdate(BaseModel):
    date: date | None = None
    workout_type: str | None = Field(None, pattern="^(strength|cardio|flexibility|other)$")
    notes: str | None = Field(None, max_length=1000)
    sets: list[ExerciseSetCreate] | None = None  # if provided, replaces all sets

class WorkoutRead(BaseModel):
    id: UUID
    client_id: UUID | None  # null only for legacy rows; API create requires client_id
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

class WorkoutListResponse(BaseModel):
    items: list[WorkoutRead]
    total: int
    page: int
    per_page: int
```

