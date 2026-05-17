---
tags: [project, fitness, backend, architecture]
title: Fitness Platform — Backend Design Spec (Part 4 — Sync protocol and AI pipeline (illustrative))
parent: Backend Design Spec
created: 2026-04-25
status: draft
---

# Part 4 — Sync protocol and AI pipeline (illustrative)

**Parent:** [Backend Design Spec (index)](Backend%20Design%20Spec.md)

**In this part:** [§6 Sync protocol](#6-sync-protocol-illustrative-planned) · [§7 AI pipeline](#7-ai-pipeline-fast-follow-illustrative)

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
