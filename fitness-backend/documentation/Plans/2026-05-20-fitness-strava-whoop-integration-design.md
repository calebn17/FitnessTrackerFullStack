# FitnessTracker — Strava & Whoop Integration Design

**Date:** 2026-05-20
**Status:** Implemented — see [../2026-05-20-strava-whoop-integration.md](../2026-05-20-strava-whoop-integration.md)
**Scope:** Phase 1a (Strava/running) + Phase 1b (Whoop/health) for the LifeDashboard
**Codebase:** `FitnessTracker/fitness-backend/`

---

## 1. Context

The LifeDashboard macOS app needs running and health data from the FitnessTracker backend. Today the backend only has workout CRUD, user management, sync, and AI evaluation domains. This spec adds:

- **Strava integration** — sync running activities, expose recent activities and aggregated summaries
- **Whoop integration** — sync sleep, recovery, and strain data, expose daily health records and summaries

Both integrations follow the existing domain-driven architecture (`models → schemas → repository → service → router`). Data syncs on-demand when dashboard endpoints are called — no background workers or webhooks for V1.

---

## 2. Decisions

| Question | Decision |
|----------|----------|
| Architecture | Approach A — two new domains (`activities` + `health`) with shared `core/oauth.py` |
| Wearable provider | Whoop first; abstraction layer supports Oura later |
| OAuth flow | Backend callback endpoints on localhost |
| Sync trigger | On-demand (`sync_if_stale()`) — no background workers |
| Sync staleness threshold | 15 minutes (configurable) |
| State storage for OAuth CSRF | In-memory dict with 5-minute TTL |

---

## 3. Domain Structure

```
app/domains/
├── activities/              # Strava integration (Phase 1a)
│   ├── models.py            # StravaActivity, OAuthToken
│   ├── schemas.py           # Pydantic request/response models
│   ├── repository.py        # DB queries for activities + tokens
│   ├── service.py           # Sync logic, stale checks, aggregate computation
│   ├── router.py            # /api/v1/activities/* + /api/v1/auth/strava/*
│   └── strava_client.py     # HTTP client wrapping Strava API
├── health/                  # Whoop integration (Phase 1b)
│   ├── models.py            # DailyHealthRecord (imports OAuthToken from activities)
│   ├── schemas.py           # Pydantic request/response models
│   ├── repository.py        # DB queries for health records + tokens
│   ├── service.py           # Sync logic, cycle→day mapping, normalization
│   ├── router.py            # /api/v1/health/* + /api/v1/auth/whoop/*
│   └── whoop_client.py      # HTTP client wrapping Whoop API
app/core/
├── oauth.py                 # Shared token exchange/refresh helpers
```

Routers registered in `main.py`:
```python
application.include_router(activities_router, prefix=settings.api_v1_prefix)
application.include_router(health_router, prefix=settings.api_v1_prefix)
```

---

## 4. Database Models

### 4a. `oauth_tokens`

Stores OAuth credentials for both providers. One row per user per provider.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, auto-generated |
| `user_id` | UUID | FK → users.id, NOT NULL |
| `provider` | String | NOT NULL (`"strava"` or `"whoop"`) |
| `access_token` | Text | NOT NULL |
| `refresh_token` | Text | NOT NULL |
| `expires_at` | DateTime(tz) | NOT NULL |
| `athlete_id` | String | Nullable — Strava athlete ID or Whoop user ID |
| `scopes` | Text | Nullable — comma-separated granted scopes |
| `last_synced_at` | DateTime(tz) | Nullable — watermark for incremental sync |
| `created_at` | DateTime(tz) | NOT NULL, server default `now()` |
| `updated_at` | DateTime(tz) | Nullable |

**Constraints:** Unique on `(user_id, provider)`.

The model definition lives in `activities/models.py` since that domain is built first. `health/models.py` imports it.

### 4b. `strava_activities`

Synced running activities from Strava.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, auto-generated |
| `user_id` | UUID | FK → users.id, NOT NULL |
| `strava_id` | BigInteger | UNIQUE, NOT NULL — dedup key |
| `sport_type` | String | NOT NULL (`"Run"`, `"TrailRun"`, `"VirtualRun"`) |
| `start_date_local` | DateTime(tz) | NOT NULL |
| `distance` | Float | NOT NULL — meters |
| `moving_time` | Integer | NOT NULL — seconds |
| `elapsed_time` | Integer | NOT NULL — seconds |
| `average_speed` | Float | NOT NULL — m/s |
| `max_speed` | Float | Nullable — m/s |
| `total_elevation_gain` | Float | NOT NULL — meters |
| `average_heartrate` | Float | Nullable — bpm |
| `max_heartrate` | Float | Nullable — bpm |
| `average_cadence` | Float | Nullable — steps/min |
| `calories` | Float | Nullable — kcal |
| `pr_count` | Integer | NOT NULL, default 0 |
| `created_at` | DateTime(tz) | NOT NULL, server default `now()` |

**Indexes:** `(user_id, start_date_local)` for time-range queries.

### 4c. `daily_health_records`

Normalized wearable data. Whoop now, Oura later — same table, differentiated by `provider`.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, auto-generated |
| `user_id` | UUID | FK → users.id, NOT NULL |
| `date` | Date | NOT NULL |
| `provider` | String | NOT NULL (`"whoop"` or `"oura"`) |
| `sleep_score` | Integer | Nullable — 0-100 |
| `total_sleep_seconds` | Integer | Nullable |
| `deep_sleep_seconds` | Integer | Nullable |
| `rem_sleep_seconds` | Integer | Nullable |
| `light_sleep_seconds` | Integer | Nullable |
| `sleep_efficiency` | Float | Nullable — percentage |
| `recovery_score` | Integer | Nullable — 0-100 |
| `resting_heart_rate` | Float | Nullable — bpm |
| `hrv` | Float | Nullable — ms |
| `spo2` | Float | Nullable — percentage |
| `strain_score` | Float | Nullable — Whoop 0-21, Oura 0-100 |
| `active_calories` | Integer | Nullable — kcal |
| `total_calories` | Integer | Nullable — kcal |
| `steps` | Integer | Nullable — Oura only |
| `created_at` | DateTime(tz) | NOT NULL, server default `now()` |
| `updated_at` | DateTime(tz) | Nullable |

**Constraints:** Unique on `(user_id, date, provider)`.
**Indexes:** `(user_id, date)`.

Most fields are nullable because incomplete data is normal (pending scores, device not worn, etc.).

---

## 5. OAuth Flow

### 5a. Strava

1. **`GET /api/v1/auth/strava/authorize`** — Returns a JSON body with the Strava OAuth redirect URL. Backend generates a `state` parameter and stores it in an in-memory dict with 5-minute TTL for CSRF validation.
2. **`GET /api/v1/auth/strava/callback?code=...&state=...`** — Validates `state`, exchanges `code` for tokens via `POST https://www.strava.com/api/v3/oauth/token`, stores tokens in `oauth_tokens`, returns success.
3. **`DELETE /api/v1/auth/strava/disconnect`** — Calls `POST https://www.strava.com/oauth/deauthorize`, deletes the `oauth_tokens` row.

Scopes: `activity:read_all`

### 5b. Whoop

1. **`GET /api/v1/auth/whoop/authorize`** — Returns Whoop OAuth redirect URL.
2. **`GET /api/v1/auth/whoop/callback?code=...&state=...`** — Exchanges code via `POST https://api.prod.whoop.com/oauth/oauth2/token`, stores tokens.
3. **`DELETE /api/v1/auth/whoop/disconnect`** — Revokes and deletes tokens.

Scopes: `read:cycles read:recovery read:sleep read:workout read:profile offline`

### 5c. Shared Token Refresh (`core/oauth.py`)

```python
@dataclass
class OAuthRefreshConfig:
    token_url: str
    client_id: str
    client_secret: str

async def ensure_valid_token(
    token: OAuthToken,
    config: OAuthRefreshConfig,
    session: AsyncSession,
) -> OAuthToken:
    """Refresh the token if it expires within 5 minutes. Updates DB in-place."""
```

Both Strava and Whoop rotate refresh tokens — the new `refresh_token` must be stored on every refresh.

### 5d. Config Additions

New fields in `Settings`:

```
strava_client_id: str = ""
strava_client_secret: str = ""
whoop_client_id: str = ""
whoop_client_secret: str = ""
```

OAuth endpoints return a clear error if the relevant credentials aren't configured.

---

## 6. Sync Logic

### 6a. Strava Activity Sync

**Initial sync** (first time after OAuth, `last_synced_at` is null):
1. Call `GET /athlete/activities?per_page=200`, paginate through all history
2. Filter for `sport_type` in `("Run", "TrailRun", "VirtualRun")`
3. Upsert each activity into `strava_activities` keyed on `strava_id`
4. Set `last_synced_at` on the `oauth_tokens` row

**Incremental sync** (`last_synced_at` exists):
1. Call `GET /athlete/activities?after=<last_sync_epoch>&per_page=200`
2. Upsert new activities
3. Update `last_synced_at`

**Staleness check:** The `/activities/recent` and `/activities/summary` endpoints call `sync_if_stale()` before querying. Stale = `last_synced_at` older than 15 minutes (configurable via `SYNC_STALENESS_MINUTES` env var). The sync is transparent to the caller.

### 6b. Whoop Health Sync

**Sync flow:**
1. Fetch cycles via `GET /developer/v2/cycle?start=<last_sync>&end=<now>`
2. For each cycle where `score_state == "SCORED"`:
   - Fetch sleep via `GET /developer/v2/activity/sleep` (batched by date range, not per-cycle)
   - Fetch recovery via `GET /developer/v2/recovery` (batched by date range)
3. Map cycle to calendar date using the cycle's `end` timestamp
4. Normalize into `daily_health_records` (see mapping below)
5. Upsert by `(user_id, date, provider)`
6. Update `last_synced_at`

**Whoop → Common Schema Mapping:**

| Common field | Whoop source | Conversion |
|-------------|-------------|------------|
| `sleep_score` | `sleep.sleep_performance_percentage` | Round to int |
| `total_sleep_seconds` | Sum of all sleep stage millis | ÷ 1000 |
| `deep_sleep_seconds` | `total_slow_wave_sleep_time_milli` | ÷ 1000 |
| `rem_sleep_seconds` | `total_rem_sleep_time_milli` | ÷ 1000 |
| `light_sleep_seconds` | `total_light_sleep_time_milli` | ÷ 1000 |
| `sleep_efficiency` | `sleep_efficiency_percentage` | Direct |
| `recovery_score` | `score.recovery_score` | Round to int |
| `resting_heart_rate` | `score.resting_heart_rate` | Direct |
| `hrv` | `score.hrv_rmssd_milli` | Direct (already in ms) |
| `spo2` | `score.spo2_percentage` | Direct |
| `strain_score` | `cycle.score.strain` | Direct (0-21 scale) |
| `active_calories` | `cycle.score.kilojoule` | × 0.239006 (kJ → kcal), round to int |
| `total_calories` | Not directly available | Nullable |
| `steps` | Not available | Null |

### 6c. Error Handling During Sync

| Scenario | Behavior |
|----------|----------|
| Token expired during sync | Auto-refresh via `core/oauth.py`, retry once |
| Refresh token revoked | Mark token invalid, return error with `provider_auth_expired` code |
| Rate limited (429) | Serve stale data from DB, include `synced_at` so dashboard shows freshness |
| Provider API down | Same as rate limited — serve stale data |

---

## 7. API Endpoints

### 7a. Activity Endpoints

**`GET /api/v1/activities/recent`**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int | 10 | Max 50 |
| `sport_type` | str | None | Optional filter |

Response:
```json
{
  "activities": [
    {
      "id": "uuid",
      "strava_id": 12345678,
      "sport_type": "Run",
      "start_date_local": "2026-05-20T07:30:00-07:00",
      "distance_meters": 8046.72,
      "distance_miles": 5.0,
      "moving_time_seconds": 2400,
      "elapsed_time_seconds": 2520,
      "pace_min_per_mile": 8.0,
      "average_speed_mps": 3.35,
      "max_speed_mps": 4.1,
      "total_elevation_gain_meters": 45.0,
      "average_heartrate": 155.0,
      "max_heartrate": 175.0,
      "average_cadence": 170.0,
      "calories": 480.0,
      "pr_count": 0
    }
  ],
  "synced_at": "2026-05-20T08:00:00Z"
}
```

`distance_miles` and `pace_min_per_mile` are computed in the schema serializer — not stored in the DB.

**`GET /api/v1/activities/summary`**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `period` | str | `"week"` | `"week"`, `"month"`, `"year"` |

Response:
```json
{
  "period": "week",
  "start_date": "2026-05-13",
  "end_date": "2026-05-20",
  "total_runs": 4,
  "total_distance_miles": 22.5,
  "total_moving_time_seconds": 10800,
  "average_pace_min_per_mile": 8.0,
  "total_elevation_gain_feet": 580.0,
  "total_calories": 2100,
  "streak_days": 3,
  "synced_at": "2026-05-20T08:00:00Z"
}
```

`streak_days` — computed by walking backwards from today counting consecutive days with at least one run. `total_distance_miles` and `total_elevation_gain_feet` are converted from stored metric values. Aggregation is done via SQL queries on `strava_activities`.

### 7b. Health Endpoints

**`GET /api/v1/health/today`**

No query params. Returns 404 with `"no_health_data"` code if no record exists for today.

Response:
```json
{
  "date": "2026-05-20",
  "provider": "whoop",
  "sleep": {
    "score": 85,
    "total_sleep_seconds": 28800,
    "deep_sleep_seconds": 7200,
    "rem_sleep_seconds": 5400,
    "light_sleep_seconds": 16200,
    "efficiency": 92.5
  },
  "recovery": {
    "score": 78,
    "resting_heart_rate": 52.0,
    "hrv": 45.0,
    "spo2": 97.5
  },
  "strain": {
    "score": 14.2,
    "active_calories": 450,
    "total_calories": 2200,
    "steps": null
  },
  "synced_at": "2026-05-20T08:00:00Z"
}
```

Response structured into `sleep`, `recovery`, `strain` sub-objects to map cleanly to dashboard sub-panels.

**`GET /api/v1/health/recent`**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 7 | Max 90 |

Response:
```json
{
  "records": [ "...same shape as /today per record..." ],
  "synced_at": "2026-05-20T08:00:00Z"
}
```

**`GET /api/v1/health/summary`**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 30 | Max 365 |

Response:
```json
{
  "period_days": 30,
  "actual_days_with_data": 27,
  "provider": "whoop",
  "avg_sleep_score": 82,
  "avg_total_sleep_hours": 7.5,
  "avg_recovery_score": 75,
  "avg_resting_heart_rate": 54.0,
  "avg_hrv": 42.0,
  "avg_strain_score": 12.8,
  "avg_active_calories": 420,
  "synced_at": "2026-05-20T08:00:00Z"
}
```

`actual_days_with_data` indicates how many of the requested days had records.

### 7c. Auth Endpoints

All require the user's JWT.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/auth/strava/authorize` | GET | Returns Strava OAuth redirect URL |
| `/api/v1/auth/strava/callback` | GET | Handles OAuth callback, stores tokens |
| `/api/v1/auth/strava/disconnect` | DELETE | Revokes + deletes Strava tokens |
| `/api/v1/auth/whoop/authorize` | GET | Returns Whoop OAuth redirect URL |
| `/api/v1/auth/whoop/callback` | GET | Handles OAuth callback, stores tokens |
| `/api/v1/auth/whoop/disconnect` | DELETE | Revokes + deletes Whoop tokens |

---

## 8. Testing Strategy

### Unit Tests
- **`strava_client.py` / `whoop_client.py`**: Mock `httpx` responses to test API response parsing, error handling, pagination
- **`service.py` (both domains)**: Mock the API clients to test sync logic — initial vs incremental, dedup, staleness checks, error recovery
- **`repository.py`**: Test queries against real Postgres (existing test fixture pattern with `migrated_database` + `db_session`)
- **`schemas.py`**: Test computed fields (`distance_miles`, `pace_min_per_mile`) and Whoop → common schema normalization
- **`core/oauth.py`**: Mock token refresh requests, test expiry detection, rotation handling

### Integration Tests
- Full endpoint tests with real DB: create user → store mock tokens → insert test activities/health records → call endpoints → verify responses
- Sync flow: mock external API, call endpoint, verify DB state after sync
- OAuth callback: mock provider token exchange, verify tokens stored correctly

### What NOT to test in CI
- Actual Strava/Whoop API calls (require real OAuth tokens)
- OAuth redirect flows (require browser interaction)

---

## 9. Alembic Migrations

Three new tables require one migration file:
1. `oauth_tokens` — with unique constraint on `(user_id, provider)`
2. `strava_activities` — with unique on `strava_id`, index on `(user_id, start_date_local)`
3. `daily_health_records` — with unique on `(user_id, date, provider)`, index on `(user_id, date)`

Single migration since all three are new tables with no dependencies on each other beyond the shared `users.id` FK.

---

## 10. Configuration Summary

New `.env` variables:

```bash
# Strava OAuth
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=

# Whoop OAuth
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=

# Sync
SYNC_STALENESS_MINUTES=15
```

All optional — endpoints return clear errors if provider credentials aren't configured.
