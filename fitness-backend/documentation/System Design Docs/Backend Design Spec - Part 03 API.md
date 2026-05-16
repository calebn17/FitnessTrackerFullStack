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

