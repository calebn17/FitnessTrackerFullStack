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
| `schemas.py` | `UserCreate`, `UserRead`, `UserUpdate` |
| `repository.py` | `get_by_id`, `get_by_email`, `create`, `update` |
| `service.py` | `get_or_create_from_supabase` — sync Supabase user on first API call |
| `router.py` | `GET /users/me` — returns current user profile |

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

```python
# app/domains/users/models.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    supabase_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

```python
# app/domains/workouts/models.py
class Workout(Base):
    __tablename__ = "workouts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), index=True)  # For sync deduplication
    date = Column(Date, nullable=False)
    workout_type = Column(String, nullable=False)  # "strength", "cardio", etc.
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    sets = relationship("ExerciseSet", back_populates="workout", cascade="all, delete-orphan")
    metrics = relationship("DerivedMetrics", back_populates="workout", uselist=False)
    insight = relationship("Insight", back_populates="workout", uselist=False)

class ExerciseSet(Base):
    __tablename__ = "exercise_sets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_id = Column(UUID(as_uuid=True), ForeignKey("workouts.id"), nullable=False)
    exercise_name = Column(String, nullable=False)
    set_number = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)  # Nullable for bodyweight exercises
    weight_unit = Column(String, default="lbs")  # "lbs" or "kg"
    rpe = Column(Float, nullable=True)  # 1-10 scale
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workout = relationship("Workout", back_populates="sets")

class DerivedMetrics(Base):
    __tablename__ = "derived_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_id = Column(UUID(as_uuid=True), ForeignKey("workouts.id"), unique=True)
    total_volume = Column(Float)  # Sum of (weight * reps) across all sets
    total_sets = Column(Integer)
    total_reps = Column(Integer)
    avg_rpe = Column(Float, nullable=True)
    exercise_count = Column(Integer)
    muscle_groups = Column(ARRAY(String))  # ["chest", "triceps", "shoulders"]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workout = relationship("Workout", back_populates="metrics")
```

```python
# app/domains/ai/models.py
class Insight(Base):
    __tablename__ = "insights"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_id = Column(UUID(as_uuid=True), ForeignKey("workouts.id"), unique=True)
    ai_output = Column(JSONB, nullable=False)  # Structured insight data
    prompt_version = Column(String)  # Track which prompt version generated this
    model_version = Column(String)  # e.g., "claude-sonnet-4-20250514"
    evaluation_score = Column(Float, nullable=True)  # Quality score 0-1
    processing_time_ms = Column(Integer)
    status = Column(String, default="pending")  # "pending", "completed", "failed"
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workout = relationship("Workout", back_populates="insight")
```

### 4.2 Database Connection

```python
# app/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

## 5. API Layer

### 5.1 Router Structure

```python
# app/main.py
from fastapi import FastAPI
from app.domains.users.router import router as users_router
from app.domains.workouts.router import router as workouts_router
from app.domains.sync.router import router as sync_router
from app.domains.ai.router import router as ai_router

app = FastAPI(
    title="Fitness Platform API",
    version="1.0.0",
)

app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(workouts_router, prefix="/api/v1/workouts", tags=["workouts"])
app.include_router(sync_router, prefix="/api/v1/sync", tags=["sync"])
app.include_router(ai_router, prefix="/api/v1/insights", tags=["insights"])
```

### 5.2 Endpoint Specifications

#### Users Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/v1/users/me` | Get current user profile | Required |
| `PUT` | `/api/v1/users/me` | Update user profile | Required |

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

### 5.3 Request/Response Schemas

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

## 6. Sync Protocol

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

## 7. AI Pipeline (Fast Follow)

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

### 8.1 Supabase JWT Validation

```python
# app/core/security.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from app.config import settings

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Supabase JWT and return/create user."""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    supabase_id = payload.get("sub")
    email = payload.get("email")
    
    # Get or create user in our database
    user_service = UserService()
    user = await user_service.get_or_create_from_supabase(
        supabase_id=supabase_id,
        email=email,
        db=db
    )
    
    return user
```

---

## 9. Configuration

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
    
    # Supabase
    supabase_url: str
    supabase_jwt_secret: str
    
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

### 11.2 Key Fixtures

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def db_session():
    """Create test database session."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
async def client(db_session):
    """Create test client with auth."""
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {TEST_JWT}"
        yield client

@pytest.fixture
def mock_anthropic(mocker):
    """Mock Claude API responses."""
    return mocker.patch("app.domains.ai.service.anthropic.AsyncAnthropic")
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
