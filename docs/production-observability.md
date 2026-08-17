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
- `/health` is the stable, process-only compatibility contract used by existing consumers and all production probes during mixed-version rollout. `/live` is the equivalent additive liveness endpoint. `/ready` executes `SELECT 1` and returns 503 on dependency failure. Independently, each web process checks the database every 30 seconds and updates availability and last-completed-check metrics, so database monitoring does not depend on probe or user traffic. A future probe switch requires the compatible image to be guaranteed deployed before the values change; it must not be reconciled independently against the currently pinned older image.
- If `/live` fails, investigate crash/OOM/configuration/startup. If only `/ready` fails, follow the database section. If Prometheus alone is down, verify the ServiceMonitor selector and monitoring NetworkPolicy before treating it as an application outage.

## Database unavailable

- Confirm `traditional_strength_dependency_available{dependency="database"}` and `traditional_strength_dependency_last_check_timestamp_seconds{dependency="database"}` across pods. The page also fires if either series is absent or the oldest check is over two minutes old; first distinguish a reported database failure from a collector/scrape failure. Check PostgreSQL provider health, connection limits, DNS/network policy, secret availability and recent migration timing.
- Do not restart healthy processes repeatedly during a database outage. Preserve the first database exception and request ID. Escalate credential or network changes through the normal production change path.
- Recovery requires every periodic collector to report availability again with a current timestamp, plus successful `/ready` and core-path smoke tests. A new successful check sets the gauge back to 1 and clears the database condition after the alert state is re-evaluated.

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

- The platform-status collector runs every five minutes. A failed Job, no success for 15 minutes, or disappearance of its last-success metric is a warning, not a page, because it affects operational freshness rather than the customer data path.
- Inspect the latest Job logs, RBAC denials, API timeouts, output volume and snapshot ingestion. Confirm a new successful timestamp and fresh portal snapshot after remediation.

## Activation and release verification

Before enabling monitoring, render the chart with `./scripts/validate-observability.sh`, confirm Prometheus selects the `release: monitoring` ServiceMonitor/PrometheusRule labels, and verify the monitoring namespace can scrape `/metrics` with the `METRICS_BEARER_TOKEN` Secret key. Public/unauthenticated requests receive 404 and the NetworkPolicy admits the private monitoring namespace only when explicitly enabled. Locally, the validator runs Helm/YAML/contract checks and runs PromQL checks when `promtool` is available; it warns without failing when the tool is absent. The authoritative `Platform Security / validate` CI job downloads Prometheus at the version and SHA-256 pinned in `.toolchain-versions.env`, sets `REQUIRE_PROMTOOL=true`, renders the enabled production `PrometheusRule`, and must pass both `promtool check rules` and `promtool test rules`. A missing tool, checksum mismatch, invalid expression, or failed representative rule evaluation fails CI. In Alertmanager, test a synthetic non-production receiver route for both `page=true` and `page=false`; do not test by creating a production outage.

After each release, verify migration success, rollout completion, `/live`, `/ready`, an authenticated paid-beta smoke path, a metrics scrape, dashboard freshness, and that no new critical alert is pending. Application deployment success without these checks is not release success.

## Known gaps

- Alertmanager receiver ownership, schedules, and delivery tests live outside this repository and must be verified before activation.
- The portal deliberately runs one Gunicorn process per pod (eight threads), so its Python counters, gauges, and histograms have one in-pod owner and are trustworthy for that pod. Horizontal replicas are aggregated by PromQL. This is not durable event storage: process restarts reset series, and `increase()` provides reset-aware window estimates rather than an audit count. Keep minimum traffic/event gates on paging rules.
- Database paging fires when any periodic observation is zero, when availability or last-check series are absent, or when the oldest last-check timestamp is over two minutes old. The separate `up` and Ready-replica alerts help distinguish database failure from scrape/pod loss. `/health` intentionally remains dependency-free, and production probes intentionally remain on it until a compatible image is guaranteed deployed.
- Argo health degradation is independent of sync state, including `Synced + Degraded`. Argo CD metrics and kube-state-metrics label allowlisting still must be confirmed in the live stack before activation. The migration alert matches the exact Helm Job name and chart labels and ignores failures more than 15 minutes after Job creation, preventing retained failures from paging indefinitely.
- There is no independent multi-region synthetic for authenticated money paths, and no PostgreSQL server-side saturation/replication alert in this repository.
