# Load tests (Phase 8)

Scripts use [k6](https://k6.io/). Install k6 locally; do not commit real JWTs.

## Prerequisites

- API running (e.g. `make dev` from `fitness-backend/`)
- Test user JWT with `sub`, `email`, `aud`, `exp` claims matching your `SUPABASE_JWT_SECRET` / audience

## Environment

| Variable   | Required | Example                          |
|-----------|----------|----------------------------------|
| `BASE_URL` | no       | `http://localhost:8000`        |
| `JWT`      | yes      | raw JWT string (no `Bearer `)  |
| `VUS`      | no       | default `1`                    |
| `DURATION` | no       | default `30s`                  |

## Run

From repository root:

```bash
cd fitness-backend
export JWT="<your-test-jwt>"
k6 run load-tests/common_flows.js
```

The default profile stays under the API's default per-IP read limit. The script asserts **p99 latency &lt; 500ms** and **error rate &lt; 5%** under the chosen load (see `options.thresholds` in `common_flows.js`). Raise `VUS` / `DURATION` only after raising test rate limits or when you intentionally want to measure `429` behavior.

## What it hits

1. `GET /health` (unauthenticated)
2. `GET /api/v1/workouts` (authenticated, first page)

Extend `common_flows.js` to add `POST /api/v1/workouts` or sync flows once you have deterministic test payloads.
