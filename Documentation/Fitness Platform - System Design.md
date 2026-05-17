---
tags:
  - project
  - fitness
  - system-design
  - architecture
  - backend
  - infrastructure
title: Fitness Platform - High-Level System Design
created: 2026-04-25
status: draft
---

# Fitness Platform - High-Level System Design

> Reference: [[Fitness App Draft]]

## 1. Overview

### Problem Statement

Build a fitness tracking platform that serves as both a functional workout logging tool and a showcase of modern backend engineering practices including event-driven architecture, AI/ML pipelines, and production-grade observability.

### Goals

| Category | Goals |
|----------|-------|
| **Product** | Workout logging (sets/reps/weight), historical tracking |
| **Engineering** | Event-driven architecture, AI evaluation pipelines, CI/CD automation, observability |

### Constraints

- MVP: Post-workout logging only (no real-time tracking)
- Single user initially (multi-tenancy in future)
- iOS-first mobile client
- Offline-first with eventual consistency

### Non-Goals (MVP)

- AI-powered insights (fast follow)
- Real-time workout tracking
- Social features
- Advanced nutrition tracking
- Android client

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                     │
│  ┌─────────────┐                        ┌─────────────┐                 │
│  │   iOS App   │ ◄── SwiftData          │   Web App   │ ◄── React/Next │
│  │  (SwiftUI)  │     (offline-first)    │   (SPA)     │                 │
│  └──────┬──────┘                        └──────┬──────┘                 │
└─────────┼──────────────────────────────────────┼────────────────────────┘
          │              HTTPS (REST/JSON)       │
          └──────────────────┬───────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        RENDER + SUPABASE                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Supabase Auth (Apple, Google, Email)                 │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                 │                                        │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │                  FASTAPI MODULAR MONOLITH                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │   │
│  │  │   Workout   │  │   Activity  │  │     AI      │               │   │
│  │  │   Domain    │  │   Domain    │  │   Domain    │               │   │
│  │  │             │  │  (Future)   │  │(Fast Follow)│               │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│      Neon       │    │     Redis       │    │   Anthropic     │
│   PostgreSQL    │    │  (Cache/Queue)  │    │   Claude API    │
│  (Serverless)   │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 3. System Components

### 3.1 iOS Client

| Aspect | Details |
|--------|---------|
| **Architecture** | MVVM with SwiftUI |
| **Local Storage** | SwiftData |
| **Auth** | Supabase Auth (Apple Sign-In, Google) |
| **Sync Strategy** | Offline-first, background sync on connectivity |
| **Conflict Resolution** | Last-write-wins with server timestamp |

**Key Responsibilities:**
- Workout logging UI
- Local persistence and caching
- Background sync queue
- Retry logic with exponential backoff

### 3.2 Web Client

| Aspect | Details |
|--------|---------|
| **Framework** | Next.js (React) |
| **Hosting** | Render Static Site (CDN) |
| **Auth** | Supabase Auth (Google, email/password) |
| **State** | React Query for server state |

**Key Responsibilities:**
- Workout logging and history viewing
- Dashboard and analytics views
- Responsive design (desktop + mobile web)

### 3.3 Backend (Modular Monolith)

A monolith with clear domain boundaries, designed to split into services if needed.

#### Workout Domain
- CRUD for workouts, exercises, sets
- Derived metrics calculation (volume, intensity)
- History queries with pagination

#### Activity Domain (Future)
- External API integrations (Strava, Apple Health)
- Activity normalization and storage

#### AI Domain (Fast Follow)
- Workout analysis pipeline
- Insight generation
- Evaluation harness for LLM outputs

**Tech Stack:**
- Python 3.11+ with FastAPI
- SQLAlchemy + Alembic (migrations)
- Pydantic for validation

### 3.4 Database Layer

**Primary:** Neon PostgreSQL (serverless)

**Migrations (implemented):** The backend ships **Alembic** migrations under `fitness-backend/alembic/versions/` (Phase 2). Local development applies them with `make migrate` after `docker compose up -d postgres`; CI runs `alembic upgrade head` before `pytest`.

**Rationale:** 
- Serverless scaling, branching for previews
- ACID compliance, JSON support
- Free tier generous for solo dev
- Native connection pooling

### 3.5 AI/ML Pipeline (Fast Follow)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Workout    │────▶│   Feature    │────▶│   Claude     │────▶│  Evaluation  │
│   Submitted  │     │  Extraction  │     │   Analysis   │     │   Harness    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                      │
                                                                      ▼
                                                               ┌──────────────┐
                                                               │   Insights   │
                                                               │   Stored     │
                                                               └──────────────┘
```

**Pipeline Stages:**
1. **Feature Extraction** — Calculate volume, intensity, muscle group targeting
2. **Claude Analysis** — Generate natural language insights via Anthropic API
3. **Evaluation Harness** — Score outputs for quality, relevance, safety
4. **Storage** — Persist validated insights to `insights` table

---

## 4. Data Model

### Entity Relationship Diagram

```
┌─────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    users    │       │    workouts     │       │  exercise_sets  │
├─────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)     │──┐    │ id (PK)         │──┐    │ id (PK)         │
│ email       │  │    │ user_id (FK)    │◄─┘    │ workout_id (FK) │◄─┐
│ created_at  │  │    │ date            │       │ exercise_name   │  │
└─────────────┘  │    │ type            │       │ reps            │  │
                 │    │ created_at      │       │ weight          │  │
                 │    └─────────────────┘       │ rpe             │  │
                 │            │                 └─────────────────┘  │
                 │            │                                      │
                 │            ▼                                      │
                 │    ┌─────────────────┐       ┌─────────────────┐  │
                 │    │ derived_metrics │       │    insights     │  │
                 │    ├─────────────────┤       ├─────────────────┤  │
                 │    │ id (PK)         │       │ id (PK)         │  │
                 │    │ workout_id (FK) │◄──────│ workout_id (FK) │◄─┘
                 │    │ volume          │       │ ai_output       │
                 └───▶│ intensity       │       │ created_at      │
                      └─────────────────┘       └─────────────────┘
```

### Table Definitions

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `users` | User accounts | id, supabase_id (unique), email, created_at |
| `workouts` | Workout sessions | id, user_id, date, type |
| `exercise_sets` | Individual sets within workout | workout_id, exercise_name, reps, weight, rpe |
| `derived_metrics` | Computed workout stats | workout_id, volume, intensity |
| `insights` | AI-generated analysis | workout_id, ai_output, created_at |

---

## 5. API Design

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | User registration |
| `POST` | `/api/v1/auth/login` | User login, returns JWT |
| `GET` | `/api/v1/users/me` | Current user profile (Bearer Supabase access JWT); creates local `users` row on first success |
| `GET` | `/api/v1/workouts` | List workouts (paginated) |
| `POST` | `/api/v1/workouts` | Create workout |
| `GET` | `/api/v1/workouts/{id}` | Get workout details with sets |
| `PUT` | `/api/v1/workouts/{id}` | Update workout |
| `DELETE` | `/api/v1/workouts/{id}` | Delete workout |
| `POST` | `/api/v1/workouts/{id}/sets` | Add exercise set |
| `GET` | `/api/v1/workouts/{id}/insights` | Get AI insights for workout |
| `POST` | `/api/v1/sync` | Batch sync endpoint for offline changes |

### Request/Response Patterns

**Create Workout Request:**
```json
{
  "date": "2026-04-25",
  "type": "strength",
  "sets": [
    {
      "exercise_name": "Bench Press",
      "reps": 8,
      "weight": 185,
      "rpe": 8
    }
  ]
}
```

**Sync Request (Batch):**
```json
{
  "client_timestamp": "2026-04-25T10:30:00Z",
  "changes": [
    {
      "operation": "create",
      "entity": "workout",
      "data": { ... },
      "client_id": "uuid"
    }
  ]
}
```

---

## 6. Data Flow

### 6.1 Workout Logging Flow

```
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│  User  │───▶│  iOS   │───▶│ Local  │───▶│ Sync   │───▶│Backend │
│ Logs   │    │  UI    │    │ Store  │    │ Queue  │    │  API   │
│Workout │    │        │    │        │    │        │    │        │
└────────┘    └────────┘    └────────┘    └────────┘    └────────┘
                                                              │
                                                              ▼
                                          ┌──────────────────────────┐
                                          │  1. Validate & Store     │
                                          │  2. Calculate Metrics    │
                                          │  3. Trigger AI Pipeline  │
                                          │  4. Return Confirmation  │
                                          └──────────────────────────┘
```

### 6.2 Offline Sync Strategy

1. **Write locally first** — All writes go to SwiftData immediately
2. **Queue for sync** — Changes added to sync queue with timestamps
3. **Background sync** — When online, process queue in order
4. **Conflict resolution** — Server timestamp wins; client gets updated state
5. **Retry with backoff** — Failed syncs retry with exponential backoff

### 6.3 AI Pipeline Flow (Fast Follow)

1. **Trigger:** Workout saved successfully
2. **Async Processing:** Job queued to Redis (or inline for MVP)
3. **Feature Extraction:** Volume, intensity, muscle groups calculated
4. **Claude API Call:** Structured prompt with workout data → Anthropic API
5. **Evaluation:** Score output for quality/relevance
6. **Storage:** Save to `insights` table
7. **Notification:** Mark insight as ready for client fetch

---

## 7. Infrastructure

### Deployment Architecture (Render + Neon)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              PRODUCTION                                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         Render                                   │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │   │
│  │  │  Static     │    │   Web       │    │  Background │          │   │
│  │  │  Site (CDN) │    │  Service    │    │   Worker    │          │   │
│  │  │  (Web App)  │    │  (FastAPI)  │    │  (AI Jobs)  │          │   │
│  │  └─────────────┘    └──────┬──────┘    └──────┬──────┘          │   │
│  └─────────────────────────────┼─────────────────┼──────────────────┘   │
│                                │                 │                      │
│            ┌───────────────────┼─────────────────┼──────────┐          │
│            ▼                   ▼                 ▼          ▼          │
│     ┌─────────────┐     ┌─────────────┐   ┌─────────────┐             │
│     │    Neon     │     │   Render    │   │  Anthropic  │             │
│     │  Postgres   │     │    Redis    │   │  Claude API │             │
│     │ (Serverless)│     │             │   │             │             │
│     └─────────────┘     └─────────────┘   └─────────────┘             │
│                                                                         │
│     ┌─────────────┐     ┌─────────────┐                                │
│     │  Supabase   │     │  Grafana    │                                │
│     │    Auth     │     │   Cloud     │                                │
│     └─────────────┘     └─────────────┘                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Environments

| Environment | Purpose | Database | Hosting |
|-------------|---------|----------|---------|
| Local | Development | Docker Postgres | `uvicorn` |
| Preview | PR previews | Neon branch | Render Preview |
| Production | Live traffic | Neon (main branch) | Render |

### CI/CD Pipeline

```
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│  Push  │───▶│  Lint  │───▶│  Test  │───▶│ Build  │───▶│ Deploy │
│        │    │        │    │        │    │ Image  │    │Staging │
└────────┘    └────────┘    └────────┘    └────────┘    └────┬───┘
                                                              │
                                          Manual Approval     │
                                                              ▼
                                                        ┌────────┐
                                                        │ Deploy │
                                                        │  Prod  │
                                                        └────────┘
```

---

## 8. Observability

### Three Pillars (Grafana Cloud)

| Pillar | Tool | Key Metrics |
|--------|------|-------------|
| **Logging** | Grafana Loki | Structured JSON logs, request/response, errors, AI pipeline |
| **Metrics** | Prometheus → Grafana | Latency (p50/p95/p99), throughput, error rates |
| **Tracing** | OpenTelemetry → Tempo | Request traces, AI pipeline timing |

### Key Dashboards

1. **API Health** — Request rate, latency, error rate by endpoint
2. **Database** — Query performance, connection pool, slow queries
3. **AI Pipeline** — Processing time, LLM latency, eval scores
4. **Sync** — Queue depth, sync success rate, conflict rate

### Alerting

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Error Rate | >5% 5xx in 5min | Critical |
| Latency Spike | p99 >2s for 5min | Warning |
| DB Connection Pool | >80% utilized | Warning |
| AI Pipeline Backlog | >100 pending jobs | Warning |

---

## 9. Security

### Authentication & Authorization

- **Auth Provider:** Supabase Auth
- **Methods:** Apple Sign-In, Google, email/password
- **Token Storage:** iOS Keychain / Web secure storage
- **API Security:** Protected routes expect `Authorization: Bearer <access_token>` (Supabase-issued HS256 JWT with `sub`, `exp`, and `aud`). The backend validates the signature and audience, then maps `sub` (+ `email` claim) to a local `users` row and syncs the stored email when it changes in Supabase. **Public routes today:** `GET /health` only; `/api/v1/users/me` requires a valid token. Misconfigured or bad tokens return **401** with a stable JSON `detail.code` (for example `token_expired`, `token_invalid_signature`, `missing_authorization`). Missing or invalid user claims after decode return **422** with `invalid_user_claims` on `GET /api/v1/users/me`.
- **Backend auth configuration:** `SUPABASE_JWT_SECRET` (JWT signing secret from the Supabase project), optional `SUPABASE_JWT_AUDIENCE` (default `authenticated`), and optional `SUPABASE_URL` (reserved for future Supabase API calls). These are read at runtime by the FastAPI settings layer.

### Data Protection

| Aspect | Approach |
|--------|----------|
| **In Transit** | TLS 1.3 for all connections |
| **At Rest** | Encrypted database storage (managed DB) |
| **PII** | Minimize collection; email only for MVP |
| **Secrets** | Environment variables, secrets manager |

### API Security

- Rate limiting per user/IP
- Input validation on all endpoints
- SQL injection prevention (parameterized queries)
- CORS configured for known clients only

---

## 10. Scalability Considerations

### Current Design (MVP)

- Single modular monolith instance
- Single Postgres instance
- No AI pipeline (fast follow)

### Scaling Path

| Bottleneck | Solution |
|------------|----------|
| API throughput | Horizontal scaling (multiple instances behind LB) |
| Database reads | Read replicas, connection pooling |
| Database writes | Vertical scaling, then sharding by user_id |
| AI pipeline | Async job queue (Redis/SQS), worker pool |
| Cache | Redis for session, frequently accessed data |

### Future Optimizations

- Event sourcing for workout history
- CQRS for read-heavy analytics queries
- CDN for static assets
- Edge caching for read endpoints

---

## 11. Open Questions / Future Work

### Resolved Decisions

- [x] **Backend:** FastAPI (Python) — fast iteration, strong AI/ML ecosystem
- [x] **Hosting:** Render — simple deploys, no K8s overhead for solo dev
- [x] **LLM Provider:** Anthropic Claude — quality analysis, strong reasoning
- [x] **Auth:** Supabase Auth — Apple Sign-In + Google + email for iOS and web

### Future Work

- **Activity Domain** — Strava integration, Apple Health sync
- **Event Bus** — Redis Streams for event-driven processing
- **Recommendation Engine** — Personalized workout suggestions
- **Android** — Native Android client
- **Social Features** — Workout sharing, challenges

---

## Appendix: Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Backend** | FastAPI (Python) | Fast iteration, async support, strong AI/ML ecosystem |
| **Database** | PostgreSQL (via Neon or Supabase) | Proven, managed serverless options, JSON support |
| **Cache** | Redis | Versatile — caching, job queues, pub/sub |
| **Hosting** | Render | Simple deploys from GitHub, no K8s complexity, scales when needed |
| **CI/CD** | GitHub Actions | Native integration, free tier, extensive marketplace |
| **LLM** | Anthropic Claude | High quality analysis, strong reasoning, good API |
| **Auth** | Supabase Auth | Apple Sign-In + Google + email, works for iOS and web |
| **Observability** | Grafana Cloud | Generous free tier, logs + metrics + traces |
