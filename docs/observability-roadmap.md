# Observability roadmap

This is the shortest safe completion path from the repository state documented
in [Observability current state](observability-current-state.md). It avoids
deploying two competing full telemetry platforms before signal ownership,
retention, privacy, and operating cost are decided.

## Guiding decisions

Before activation, platform and application owners should record four choices:

1. **System of record per signal.** Use Prometheus for Kubernetes/application
   metrics. Choose either Log Analytics or Loki as the primary application-log
   investigation store. Choose either Application Insights or Tempo as the
   primary trace store. Dual-write only for a time-boxed migration with a cost
   and deletion plan.
2. **Data safety.** Define an attribute and log-field allowlist. Exclude request
   bodies, form values, cookies, authorization headers, database URLs, and
   athlete/coach personal data. Test redaction before exporting telemetry.
3. **Reliability target.** Agree the public availability SLI, latency SLI,
   objective, measurement window, and paging burn rates. Dashboard thresholds
   alone are not an SLO.
4. **Ownership and spend.** Name the application owner, platform owner, alert
   responder, retention limits, storage class, and monthly ingestion guardrail.

## Sequenced completion path

| Order | Outcome | Minimum safe work | Dependencies | Completion evidence |
|---:|---|---|---|---|
| 1 | Honest production health | Keep current startup/readiness/liveness probes on the portal's shallow `/health` route. If dependency-aware readiness is later required, add a separate portal route with a strict database timeout before changing the readiness probe; test healthy, degraded, and timeout cases. | Application/database owners; probe budget lower than request timeout. | Current render proves all production probes use `/health`; future route work requires unit tests and a rendered Deployment before activation. |
| 2 | Production Prometheus metrics | Instrument `platform-portal` with bounded-label request count/duration metrics and a private `/metrics` route; exclude scrape/probe noise. Keep the `ServiceMonitor` behind both `monitoring.enabled` and `monitoring.serviceMonitor.enabled`, enable monitoring NetworkPolicy ingress, and add route/metric tests. The root `app/app.py` tests remain a reference, not production evidence. | Prometheus Operator CRDs and a confirmed release/selector label; privacy review for labels. | A staging target is `UP`; a known request changes the expected counter and histogram; no path, user, or query-string cardinality leak. |
| 3 | Declarative Prometheus stack | Manage a pinned `kube-prometheus-stack` release through the existing GitOps model. Configure selectors, storage/retention, resource limits, authentication/ingress policy, backups if persistence is required, and version/CRD upgrade procedure. | Storage and cost decision; DNS/TLS/auth if externally accessed; operator compatibility. | GitOps health, all expected targets `UP`, rule evaluation healthy, persistence/restart test, and no unintended public endpoint. |
| 4 | Grafana as code | Provision the Prometheus data source and sidecar, enable the existing dashboard only after fixing queries against real labels, and add datasource/dashboard health checks. Pin dashboard UID and ownership metadata. | Step 3; Grafana access-control and secret delivery. | Dashboard loads after a clean reconcile and pod restart; panels return expected staging series without query errors. |
| 5 | Actionable metric alerts | Validate proposed rules with real label sets, then start with public/private availability, ready replicas, rollout failure, and two multi-window SLO burn-rate alerts. Configure grouping, inhibition, owner labels, and a dead-man alert. | SLO decision; Alertmanager installed; every page has a tested runbook. | Synthetic alert reaches a non-production receiver, resolves correctly, groups as designed, and records delivery latency. |
| 6 | Azure baseline completion | Keep workspace-based Application Insights and AKS Container Insights only if chosen as signal systems of record. Add Terraform for diagnostic settings, DCR associations as applicable, sampling/caps, public availability test, action group, and a minimal alert set. Remove or redesign the orphan VM DCR. | Azure owner; destination/action-group identifiers supplied outside Git; cost and data residency approval. | Terraform validation/plan review and a staged synthetic failure demonstrating telemetry and notification without exposing secrets. |
| 7 | Structured logging | Emit JSON to stdout with timestamp, severity, service, environment, safe request/trace ID, event name, and exception class. Add redaction and cardinality tests. Decide retention and queries before raising verbosity. | Data classification; correlation format; chosen log backend. | Tests prove forbidden fields are absent; a staging request can be found by correlation ID. |
| 8a | Loki, only if selected | Deploy a pinned Loki mode sized for the workload, object storage or explicitly accepted ephemeral storage, retention/deletion, limits, auth/tenant boundary, and a supported Kubernetes log collector. Provision the Grafana data source and alerts for ingestion failures. | Steps 3, 4, and 7; object-store credentials via approved secret delivery; Log Analytics duplication decision. | Fresh staging logs query by service/correlation ID, retention works, restart does not lose data beyond the accepted design, and ingestion failure alerts. |
| 8b | Production tracing | Instrument `platform-portal` and database/client libraries through an OpenTelemetry SDK or Collector. Set stable resource attributes, W3C propagation, parent-based sampling, exception controls, and span-attribute allowlists. | Privacy review; trace backend decision; egress/secret delivery; version-pinned dependencies. | One staging transaction shows server and PostgreSQL spans with shared trace context and no sensitive attributes. |
| 9 | Tempo, only if selected | Deploy pinned Tempo with OTLP ingestion, durable storage/retention, limits, authentication/network isolation, and Grafana data source. Prefer an OpenTelemetry Collector for buffering, retries, filtering, and backend portability; monitor refused/dropped spans and queue pressure. | Steps 4 and 8b; object storage; collector capacity and failure policy; Application Insights duplication decision. | Trace lookup from Grafana succeeds after restart; dropped-span failure is visible and alerts; trace-to-log correlation works if Loki was selected. |
| 10 | Operationalize | Expand and exercise runbooks, add telemetry-pipeline dashboards, review noise and cost after two weeks, then tune thresholds/sampling/retention. Schedule restore and upgrade tests. | Stable signals and routing from prior steps; named responders. | Recorded game-day outcomes, alert/runbook ownership review, measured false-positive rate, cost report, and tracked follow-ups. |

Steps 8a and 9 are optional architecture choices, not prerequisites for reliable
monitoring. The shortest path is Prometheus + Grafana + Alertmanager for metrics,
with the already-provisioned Azure services for logs and traces after production
instrumentation is added. Loki and Tempo should be introduced only when their
operational benefit justifies storage, upgrades, backups, and on-call burden.

## Component-specific dependencies and guardrails

### Prometheus

- Requires a pinned Prometheus Operator stack and matching CRDs before the
  application chart can safely create `ServiceMonitor` or `PrometheusRule`.
- Keep `/metrics` private and allow ingress only from the monitoring namespace.
- Bound every label. Route templates or low-cardinality endpoint names are safe;
  raw URLs, user IDs, database statements, and exception messages are not.
- Monitor Prometheus itself: target failures, rule errors, storage pressure,
  ingestion/sample limits, and configuration reload failures.

### Grafana

- Provision data sources and dashboards declaratively; do not depend on manual UI
  state or screenshots.
- Use least-privilege access and approved secret references. Do not embed
  credentials in dashboard JSON.
- Test dashboard queries during staging because JSON syntax validation cannot
  detect wrong metric names or labels.

### Alertmanager and Azure alerting

- Keep receiver credentials outside Git. Reference an approved secret mechanism.
- Define severity, business hours, grouping, inhibition, retry, escalation,
  acknowledgement, and ownership before enabling pages.
- Avoid duplicate paging from Prometheus and Azure for the same failure. Nominate
  one paging source and leave the other as diagnostic or fallback coverage.
- Test firing and recovery delivery; a syntactically valid rule is insufficient.

### Loki

- Decide first whether Log Analytics already meets the need. Running both can
  duplicate sensitive data and ingestion cost.
- Prefer a supported collector with position persistence, backpressure, and
  Kubernetes metadata controls. Drop high-cardinality labels and unwanted
  namespaces at collection time.
- Define deletion, retention, storage encryption, backup/restore expectations,
  and query limits before production ingestion.

### OpenTelemetry and Tempo

- A Collector provides filtering, batching, retry, sampling, and backend
  portability, but it becomes a monitored production dependency.
- Use resource attributes such as service name, deployment environment, version,
  and Kubernetes identity; do not attach user or form data.
- Make overload behavior explicit: bounded queues and observable dropping are
  safer than unbounded application memory growth.
- If Application Insights remains the trace backend, Tempo is not required.

## Minimum runbook set

Each alert annotation should link to a versioned section containing symptoms,
impact, safe queries, decision points, mitigation, rollback, escalation owner,
and verification. Add these runbooks before enabling the related page:

- public endpoint unavailable and private scrape unavailable;
- high SLO burn rate, elevated errors, and elevated latency;
- pod not Ready, rollout stalled, restart/OOM, and resource saturation;
- PostgreSQL dependency failure and migration Job failure;
- Prometheus target/rule/storage failure;
- Grafana dashboard or data-source failure;
- Alertmanager delivery failure and dead-man alert absence;
- log collection/backpressure/storage failure for the chosen log backend;
- trace export, collector queue, or backend ingestion failure;
- telemetry cost/volume anomaly and emergency sampling or retention reduction.

Runbooks must avoid commands that print Kubernetes Secrets, connection strings,
request bodies, or personal data. Practice the first five in staging before
production alert activation, and repeat after material stack upgrades.

## Deferred until justified

- Multi-cluster/federated Prometheus, Thanos/Mimir, high-availability Loki, and
  high-availability Tempo are disproportionate until retention, query load, and
  recovery objectives demand them.
- Service-mesh telemetry is unnecessary for the current single-application
  topology.
- A second dashboard or alerting platform should not be added merely to mirror
  the first; use cross-links and explicit signal ownership instead.
