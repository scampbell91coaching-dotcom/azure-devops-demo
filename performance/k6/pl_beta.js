import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";

const baseUrl = (__ENV.BASE_URL || "http://127.0.0.1:5000").replace(/\/$/, "");
const profile = __ENV.PROFILE || "smoke";
const profiles = {
  smoke: { duration: "30s", coach: 1, athlete: 1, factory: 0 },
  beta: { duration: "8m", coach: 6, athlete: 24, factory: 2 },
  peak: { duration: "5m", coach: 12, athlete: 48, factory: 4 },
};

if (!profiles[profile]) fail(`Unknown PROFILE=${profile}`);
const target = new URL(baseUrl);
const loopback = ["localhost", "127.0.0.1", "::1"].includes(target.hostname);
if (!loopback && __ENV.PL_ALLOW_REMOTE !== "true") {
  fail("Remote load is disabled. Use localhost or explicitly approve a disposable environment with PL_ALLOW_REMOTE=true.");
}

const selected = profiles[profile];
const scenarios = {
  coach_reads: workload("coachJourney", selected.coach, selected.duration),
  athlete_reads: workload("athleteJourney", selected.athlete, selected.duration),
};
if (selected.factory > 0) scenarios.factory_preview = workload("factoryPreview", selected.factory, selected.duration);
if (__ENV.ENABLE_WRITES === "true") scenarios.session_progress = workload("sessionProgress", Math.max(1, Math.floor(selected.athlete / 8)), selected.duration);

export const options = {
  scenarios,
  thresholds: {
    "http_req_failed{class:html}": ["rate<0.01"],
    "http_req_duration{class:html}": ["p(95)<750", "p(99)<1500"],
    "http_req_failed{class:api}": ["rate<0.005"],
    "http_req_duration{class:api}": ["p(95)<500", "p(99)<1000"],
    "http_req_failed{class:write}": ["rate<0.01"],
    "http_req_duration{class:write}": ["p(95)<750", "p(99)<1500"],
    "http_req_failed{class:factory}": ["rate<0.01"],
    "http_req_duration{class:factory}": ["p(95)<2000", "p(99)<4000"],
    "http_req_failed{class:meal_plan}": ["rate<0.01"],
    "http_req_duration{class:meal_plan}": ["p(95)<1000", "p(99)<2000"],
  },
};

function workload(fn, vus, duration) {
  return { executor: "constant-vus", exec: fn, vus, duration, gracefulStop: "15s" };
}

function required(name) {
  const value = __ENV[name];
  if (!value) exec.test.abort(`${name} is required for this scenario`);
  return value;
}

function params(cookie, name, metricClass = "html") {
  return { headers: { Cookie: cookie }, redirects: 0, tags: { name, class: metricClass } };
}

function get(path, cookie, name, metricClass = "html", statuses = [200]) {
  const response = http.get(`${baseUrl}${path}`, params(cookie, name, metricClass));
  check(response, { [`${name} status`]: (r) => statuses.includes(r.status) });
  return response;
}

export function coachJourney() {
  const cookie = required("COACH_COOKIE");
  const athlete = required("ATHLETE_ID");
  const block = __ENV.BLOCK_ID;
  const pick = Math.floor(Math.random() * 5);
  if (pick === 0) get("/coach", cookie, "coach_dashboard");
  else if (pick === 1) get(`/athletes/${athlete}`, cookie, "coach_athlete_detail");
  else if (pick === 2) get("/check-ins", cookie, "coach_checkins");
  else if (pick === 3) get("/nutrition", cookie, "coach_nutrition");
  else get(`/api/v1/athletes/${athlete}/performance/charts${block ? `?block_id=${block}` : ""}`, cookie, "performance_charts", "api");
  sleep(1 + Math.random() * 3);
}

export function athleteJourney() {
  const cookie = required("ATHLETE_COOKIE");
  const athlete = required("ATHLETE_ID");
  const session = required("SESSION_ID");
  const pick = Math.floor(Math.random() * 10);
  if (pick < 3) get("/athlete/dashboard", cookie, "athlete_dashboard");
  else if (pick < 6) get(`/athlete/programme/sessions/${session}`, cookie, "athlete_session");
  else if (pick === 6) get(`/athletes/${athlete}/check-ins/new`, cookie, "athlete_checkin_form");
  else if (pick === 7) get("/athlete/check-ins", cookie, "athlete_checkin_history");
  else if (pick === 8) get("/athlete/nutrition-targets", cookie, "athlete_nutrition");
  else get(__ENV.MEAL_PLAN_PDF_PATH || "/athlete/meal-plan", cookie, __ENV.MEAL_PLAN_PDF_PATH ? "meal_plan_pdf" : "meal_plan_html", "meal_plan", [200, 404]);
  sleep(2 + Math.random() * 5);
}

export function factoryPreview() {
  const cookie = required("COACH_COOKIE");
  const athlete = required("ATHLETE_ID");
  const response = http.post(`${baseUrl}/programming/factory/preview`, {
    athlete_id: athlete, name: "Disposable load preview", week_count: "4",
    training_days: "4", template_type: "SBD",
  }, params(cookie, "block_factory_preview", "factory"));
  check(response, { "factory preview status": (r) => r.status === 200 });
  sleep(4 + Math.random() * 6);
}

export function sessionProgress() {
  const cookie = required("ATHLETE_COOKIE");
  const session = required("SESSION_ID");
  const csrf = required("CSRF_TOKEN");
  const response = http.post(`${baseUrl}/athlete/programme/sessions/${session}`, {
    csrf_token: csrf, action: "save",
  }, params(cookie, "session_progress_save", "write"));
  check(response, { "session save handled": (r) => [200, 302, 400].includes(r.status) });
  sleep(8 + Math.random() * 12);
}

