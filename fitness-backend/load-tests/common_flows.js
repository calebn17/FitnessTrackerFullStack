/**
 * k6 load script for common API flows (Phase 8).
 *
 * Required environment variables:
 *   BASE_URL       e.g. http://localhost:8000
 *   JWT            Bearer token (test user; do not commit real tokens)
 *
 * Optional:
 *   VUS            virtual users (default 1; keep low unless rate limits are raised)
 *   DURATION       e.g. 30s, 1m (default 30s)
 *
 * Run: k6 run load-tests/common_flows.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const healthDuration = new Trend("health_duration_ms");
const listDuration = new Trend("workouts_list_duration_ms");
const errorRate = new Rate("errors");

const base = __ENV.BASE_URL || "http://localhost:8000";
const token = __ENV.JWT || "";

export const options = {
  vus: Number(__ENV.VUS || 1),
  duration: __ENV.DURATION || "30s",
  thresholds: {
    http_req_duration: ["p(99)<500"],
    errors: ["rate<0.05"],
  },
};

function headers() {
  const h = { "Content-Type": "application/json" };
  if (token) {
    h.Authorization = `Bearer ${token}`;
  }
  return h;
}

export default function () {
  const h = headers();

  const healthRes = http.get(`${base}/health`);
  healthDuration.add(healthRes.timings.duration);
  const healthOk = check(healthRes, {
    "health 200": (r) => r.status === 200,
  });
  if (!healthOk) {
    errorRate.add(1);
  } else {
    errorRate.add(0);
  }

  if (!token) {
    sleep(0.5);
    return;
  }

  const listRes = http.get(`${base}/api/v1/workouts?page=1&per_page=20`, { headers: h });
  listDuration.add(listRes.timings.duration);
  const listOk = check(listRes, {
    "workouts list 200": (r) => r.status === 200,
  });
  if (!listOk) {
    errorRate.add(1);
  } else {
    errorRate.add(0);
  }

  sleep(1);
}

export function setup() {
  if (!token) {
    throw new Error("Set JWT to a valid test Bearer token (export JWT=...).");
  }
}
