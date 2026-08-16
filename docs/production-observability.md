# Production observability and incident runbook

This runbook covers the paid-beta `traditional-strength` service. Prometheus rules and the Grafana dashboard are deliberately opt-in (`monitoring.enabled=false`) until the production Prometheus selector and Alertmanager route are verified. Enabling them is a reviewed GitOps change; do not apply chart output by hand.

The measurable product objectives and release evidence contract remain in [paid-beta-slos-and-python-skips.md](paid-beta-slos-and-python-skips.md); this document defines the operational response to their production signals.

## Severity and routing

| Severity | Meaning | Route | Response target |
|---|---|---|---|
| `critical` / `page=true` | Customers cannot use a core path, the database is unavailable, or a release/migration may be unsafe | On-call page | Acknowledge in 5 minutes; mitigate in 30 minutes |
| `warning` / `page=false` | Degradation, capacity risk, collector failure, or security anomaly without proven customer outage | Team notification/ticket | Review in business hours; within 30 minutes during a release |
| `info` / `page=false` | Trend or audit signal | Dashboard/digest | No immediate response |

Route on `page`, not only `severity`. Inhibit warnings for the same service while a critical alert is active. Group by `service` and `alertname`; repeat pages no more often than every two hours. Never put emails, tenant IDs, object IDs, tokens, or query strings in alert labels.

Paging thresholds require persistence and, where traffic is involved, a minimum sample: no scrape target for 5 minutes; fewer Ready replicas for 5 minutes; database unavailable for 2 minutes; at least 5 errors, 20 requests, and over 10% 5xx for 5 minutes; p95 over 3 seconds with 20 requests for 10 minutes; migration failure after 1 minute; stalled/degraded release for 10 minutes. Repeated 5xx below the page gate, p95 from 1–3 seconds, saturation, restarts, auth/tenant anomalies, and collector failures are non-paging.

## First five minutes

1. Confirm the alert is current in Prometheus and check the dashboard around the firing time. Silence only a known duplicate, never the underlying signal.
2. Correlate `X-Request-ID` from a failed response with structured application logs. Logs contain route templates, not query strings or tenant identifiers.
3. Check desired versus Ready replicas, pod events/restarts, the most recent deployment revision, and recent migration/collector Jobs. Read-only examples: `kubectl -n production get deploy,pods,jobs,cronjobs`; `kubectl -n production describe deploy flask-web`.
4. Identify the last known-good immutable image and release revision. Rollback or retry remains a separate, approved GitOps action.

## Web unavailable or not ready

- Compare Prometheus `up`, desired/available replicas, probe failures, container logs, events, CPU/memory and the database readiness panel.
- `/live` proves only that the process can serve HTTP. `/ready` and `/health` execute `SELECT 1`; a 503 removes a pod from traffic without causing liveness restarts.
- If `/live` fails, investigate crash/OOM/configuration/startup. If only `/ready` fails, follow the database section. If Prometheus alone is down, verify the ServiceMonitor selector and monitoring NetworkPolicy before treating it as an application outage.

## Database unavailable

- Confirm `traditional_strength_dependency_available{dependency="database"}` and readiness failures across pods. Check PostgreSQL provider health, connection limits, DNS/network policy, secret availability and recent migration timing.
- Do not restart healthy processes repeatedly during a database outage. Preserve the first database exception and request ID. Escalate credential or network changes through the normal production change path.
- Recovery requires stable readiness across all desired replicas and successful core-path smoke tests, not merely one successful probe.

## HTTP errors or latency

- Break down 5xx by route/status and latency by route. Exclude `/metrics`; probe traffic is visible but should not dominate a paid-beta workload.
- Use request IDs to inspect exceptions and upstream dependency spans. Compare the onset with releases, database latency, pod saturation and restarts.
- Page only at the documented error/latency gates. A few low-volume errors create a warning for investigation without waking on-call.

## Authentication or tenant-denial anomaly

- Login metrics distinguish `failed`, `rate_limited`, and `success`; authorization metrics distinguish unauthenticated, forbidden, and concealed-object outcomes. Tenant metrics use bounded reasons only.
- Check whether the increase follows a UI/API release, a single source pattern in protected logs, or broad customer reports. Do not weaken tenant checks or disclose concealed object existence while investigating.
- These alerts are non-paging by default. Escalate to a security incident if there is credible automated abuse, cross-tenant access, or account compromise; page separately if login availability is materially affected.

## Resource pressure

- Check CPU/memory against requests and limits, throttling/OOM events, request rate and HPA current/max replicas. Sustained max replicas or over 85% CPU/90% memory is a warning.
- Page only when pressure also causes availability, 5xx, or critical latency symptoms. Capacity changes require a reviewed values change and load evidence.

## Migration or release failure

- A failed migration is paging because schema state may block or mismatch the release. Stop promotion, retain failed Job logs/events, and establish whether the transaction rolled back before any retry.
- Never rerun migrations with runtime credentials or edit the database manually. Use the separate migration secret and the existing migration verification tooling.
- For a stalled rollout or degraded Argo application, compare desired revision, image digest/tag, migration result and pod events. Restore the last known-good Git revision through the approved GitOps workflow.

## Status collector stale or failed

- The collector runs every five minutes. A failed Job or no success for 15 minutes is a warning, not a page, because it affects operational freshness rather than the customer data path.
- Inspect the latest Job logs, RBAC denials, API timeouts, output volume and snapshot ingestion. Confirm a new successful timestamp and fresh portal snapshot after remediation.

## Activation and release verification

Before enabling monitoring, render the chart with `./scripts/validate-observability.sh`, confirm Prometheus selects the `release: monitoring` ServiceMonitor/PrometheusRule labels, verify network access to `/metrics`, and use `promtool check rules` against the rendered rule group when `promtool` is available. In Alertmanager, test a synthetic non-production receiver route for both `page=true` and `page=false`; do not test by creating a production outage.

After each release, verify migration success, rollout completion, `/live`, `/ready`, an authenticated paid-beta smoke path, a metrics scrape, dashboard freshness, and that no new critical alert is pending. Application deployment success without these checks is not release success.

## Known gaps

- Alertmanager receiver ownership, schedules, and delivery tests live outside this repository and must be verified before activation.
- Prometheus Python metrics are process-local under the current two-worker Gunicorn configuration; counters and histograms can be under-reported depending on which worker serves a scrape. Configure Prometheus multiprocess mode or use one worker per horizontally scaled pod before relying on exact totals at larger scale.
- Argo CD metrics and kube-state-metrics label availability must be confirmed in the live stack; absent release metrics currently fail quiet rather than page.
- There is no independent multi-region synthetic for authenticated money paths, and no PostgreSQL server-side saturation/replication alert in this repository.
