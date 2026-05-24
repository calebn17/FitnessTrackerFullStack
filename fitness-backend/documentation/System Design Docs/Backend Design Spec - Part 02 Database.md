---
tags: [project, fitness, backend, architecture]
title: Fitness Platform — Backend Design Spec (Part 2 — Database layer)
parent: Backend Design Spec
created: 2026-04-25
status: draft
---

# Part 2 — Database layer

**Parent:** [Backend Design Spec (index)](Backend%20Design%20Spec.md)

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
| `DerivedMetrics` | same | `derived_metrics` | One row per workout (`workout_id` unique); `muscle_groups` as `TEXT[]`; row is created/updated by the workouts service when sets change (Phase 5) |
| `Insight` | `app/domains/ai/models.py` | `insights` | `workout_id` unique; `ai_output` `JSONB`; `status` default `'pending'` |
| `OAuthToken` | `app/domains/activities/models.py` | `oauth_tokens` | One row per `(user_id, provider)`; Strava + Whoop credentials |
| `StravaActivity` | same | `strava_activities` | `strava_id` unique; running activities synced from Strava |
| `DailyHealthRecord` | `app/domains/health/models.py` | `daily_health_records` | Unique `(user_id, date, provider)`; normalized wearable metrics |

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

**Migrations:** Alembic async env in `alembic/env.py`; revisions under `alembic/versions/phase2_0*.py` (including `phase2_05_integrations` for `oauth_tokens`, `strava_activities`, `daily_health_records`). Run `make migrate` from `fitness-backend/`.

---
