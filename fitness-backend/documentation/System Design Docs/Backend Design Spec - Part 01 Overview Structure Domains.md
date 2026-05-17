---
tags: [project, fitness, backend, architecture]
title: Fitness Platform — Backend Design Spec (Part 1 — Overview, project structure, and domain architecture)
parent: Backend Design Spec
created: 2026-04-25
status: draft
---

# Part 1 — Overview, project structure, and domain architecture

**Parent:** [Backend Design Spec (index)](Backend%20Design%20Spec.md)

**In this part:** [§1 Overview](#1-overview) · [§2 Project structure](#2-project-structure) · [§3 Domain architecture](#3-domain-architecture)

---

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

