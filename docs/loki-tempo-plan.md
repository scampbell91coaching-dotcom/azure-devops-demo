# Loki and Tempo integration plan

Status: implementation-ready design; no Loki, Tempo, Grafana, collector, Azure
resource, or live cluster configuration is created by this change.

## Scope and current-state audit

The production workload is the `platform-portal/Dockerfile` image deployed by
`flask-app`. Gunicorn runs its `app:app` entry point on port 8090. The portal
exposes `/health`, but not `/ready` or `/metrics`, and it does not configure
Prometheus or OpenTelemetry instrumentation. Health probes, a disabled-by-default
Grafana dashboard, and disabled Prometheus rules exist in the chart. The
`ServiceMonitor` is also disabled and renders only when both monitoring flags are
true. There is no OpenTelemetry Collector, OTLP endpoint, log agent, Loki, Tempo,
or object-store configuration.

The root `app/app.py` service is a reference/demo on port 5000. It contains
Prometheus metrics, `/ready`, `/metrics`, conditional Azure Monitor setup, and
structured request/trace correlation with focused tests. It is not the current
production image, so none of those endpoints or signals demonstrates portal
telemetry. The production portal currently relies on Gunicorn stdout/stderr and
has no consistent JSON schema, request ID, or explicit trace fields.

The production image, chart container port, and Service target agree on 8090.
Before implementation, verify installed Prometheus/Grafana versions, CRDs,
Grafana sidecar configuration, ingress-controller log format, daily volume, or
AKS node/container runtime log paths. Resolve those facts from a non-secret,
sanitised inventory rather than treating this document as live-state evidence.

## Signal contract and correlation

Use W3C Trace Context end to end. NGINX must forward `traceparent` and
`tracestate`; OpenTelemetry Flask instrumentation should continue the valid
incoming trace or create a new one. Do not use `X-Request-ID` as a trace ID.

| Field | Contract |
|---|---|
| `trace_id` | 32 lowercase hexadecimal characters from the active span; absent when no valid span exists |
| `span_id` | 16 lowercase hexadecimal characters from the active span; absent when no valid span exists |
| `request_id` | Caller `X-Request-ID` only when it is a 32-digit hexadecimal or canonical UUID value; otherwise a random 32-character value; returned in the response |
| `service` | Stable low-cardinality name, currently `flask-web` |
| `event` | Stable event name, currently `http_request_completed` |
| `route` | Flask route template such as `/health`, never the raw URL |
| `timestamp` | UTC RFC 3339 application timestamp; Loki should also use collector ingestion time if clock skew is detected |

The collector must parse JSON and retain the fields in the log body/structured
metadata. Loki stream labels are limited to `cluster`, `namespace`, `service`,
`environment`, `container`, and `level`. Never label `trace_id`, `span_id`,
`request_id`, pod UID, route, user, athlete, or any database identifier. Grafana
must configure Loki derived fields for `trace_id` using
`trace_id\"?:\"?([0-9a-f]{32})` and link to the Tempo data source with the captured
value. Configure Tempo-to-Loki trace-to-logs with the same service/namespace
labels and a narrow span time window. Configure Tempo service graphs/span
metrics to the existing Prometheus only after their extra series are budgeted.

## Target architecture

Use an OpenTelemetry Collector **agent DaemonSet** for container stdout and node
metadata, plus a small **gateway Deployment** for OTLP traces. Agents read the
Kubernetes container log files through the `filelog` receiver, parse CRI and
application JSON, enrich through `k8sattributes`, apply redaction and batching,
then write logs to Loki. Application traces go by OTLP to the gateway, which
applies memory limiting, tail sampling and batching, then exports to Tempo.
During migration, fan out traces to the existing Azure Monitor path only through
a deliberately tested exporter; do not accidentally double-export from both the
application and collector. Keep direct Application Insights export until Tempo
queries and failure drills pass.

For this small platform, begin with pinned, supported Loki and Tempo Helm chart
versions in single-binary/monolithic mode with one replica each in a staging
environment. Production durability requires Azure Blob-compatible object
storage and must not rely on pod filesystem or the chart's test MinIO. Move to
simple-scalable/distributed components only when measured ingest, availability,
or query concurrency requires it. Grafana remains the existing instance; add
provisioned data sources instead of another Grafana installation.

Network flow should be explicit: application pods to collector gateway OTLP/gRPC
4317 (or OTLP/HTTP 4318), agents to Loki gateway 3100, collector gateway to Tempo
4317, and Grafana to Loki 3100 and Tempo 3200. Deny public ingress. Restrict
namespace selectors and service accounts, retain `automountServiceAccountToken:
false` where Kubernetes discovery is not needed, and grant the agent only the
read-only metadata/RBAC and host-log mounts required by `filelog`.

## Retention, sampling and capacity

Start with 7 days of application logs and 72 hours of traces. Keep the existing
Application Insights/Log Analytics policy unchanged during evaluation. Loki
compactor retention and Tempo block retention must be enabled explicitly; Azure
Blob lifecycle rules are a backstop, not the primary deletion mechanism. Any
legal or operational need for longer retention requires privacy and cost review.

Start trace sampling with all errors and latency above 1 second retained, plus
10% of other server traces, decided at the collector gateway. Health and metrics
spans should be dropped. Tail sampling needs enough memory to hold the decision
window; test dropped-span and OOM behavior under peak concurrency. If direct
Azure sampling remains active, record that its population may differ from Tempo.

Before sizing, measure for at least seven representative days: log bytes/day
after parsing, spans/second and bytes/span at peak, active Loki streams, query
concurrency, compression ratio, and object-store requests/egress. Set namespace
ResourceQuota and component requests/limits from those measurements. Create
alerts for rejected samples, collector queue saturation/export failures,
Loki/Tempo ingestion errors, compactor failures, object-store errors, disk use,
and query latency. Set per-tenant ingestion, stream, query and retention limits.
Treat unbounded labels and duplicate Azure/Tempo export as cost incidents.

## Privacy and security controls

Telemetry is operational data, not an audit record. Allowlist fields; never
collect request/response bodies, query strings, cookies, authorization headers,
tokens, connection strings, email, free text, athlete data, full SQL statements,
or stack-local values likely to contain them. Hashing an identifier does not
make it non-personal. Keep the current database ID business log out of broadly
accessible streams or remove/generalise it before portal logs are onboarded.

Collector processors must delete known sensitive keys before export and truncate
oversized bodies. Validate with seeded canary secrets and synthetic personal
data, then assert neither appears in Loki, Tempo attributes, collector logs, nor
dead-letter/debug output. Disable collector debug exporters in production.
Encrypt transport in-cluster where the selected charts support it and require
TLS/workload identity to Azure storage. Store storage details in Key Vault and
sync references through the established External Secrets pattern; never put
credentials in Helm values, Terraform plans, or evidence. Use Azure workload
identity rather than account keys where chart support has been verified. Apply
Grafana least-privilege teams/data-source permissions and audit query access.

## Deferred repository changes

Implement these in separate reviewed changes, in this order:

1. Add an ADR selecting deployment modes, chart/application versions, tenant
   model, availability target, ownership and the temporary Application Insights
   coexistence period. Pin charts by version and container images by digest.
2. Add Terraform for dedicated storage accounts/containers (separate Loki and
   Tempo), private endpoints/DNS where supported, lifecycle backstops, encryption,
   diagnostic settings, workload identities and narrowly scoped Blob Data roles.
   Expose only non-secret resource identifiers. Run `terraform plan`; deployment
   requires separate approval and is outside this plan.
3. Add GitOps Helm releases or Argo CD Applications for `grafana/loki`,
   `grafana/tempo` and `open-telemetry/opentelemetry-collector`. Values must set
   retention, schemas, object storage, resources, persistence/WAL where required,
   topology, PodDisruptionBudgets, security contexts, service accounts, limits,
   and monitoring. Disable bundled Grafana and MinIO.
4. Add namespace-scoped NetworkPolicies and RBAC. Add ExternalSecrets containing
   references only if workload identity is not supported. Add ServiceMonitors and
   PrometheusRules for every pipeline component.
5. Provision Grafana Loki/Tempo data sources with stable UIDs, derived fields,
   trace-to-logs/logs-to-traces, and optional service-map settings. Use
   provisioning files/Secrets, not click-ops.
6. Change `flask-web` from the direct Azure distribution to explicit upstream
   OpenTelemetry SDK/OTLP configuration only after a compatibility test confirms
   Flask, requests and database instrumentation. Set standard resource
   attributes: `service.name`, `service.version`, `deployment.environment.name`,
   and Kubernetes attributes supplied by the collector. Never place high-cardinality
   values in resource attributes.

Every chart addition needs `helm lint`, deterministic `helm template`, schema
validation against the target CRDs/Kubernetes version, policy/security scans,
and tests asserting no public Service, no plaintext secret, retention enabled,
storage not ephemeral, resource limits present, and network policies restrict
ingress/egress. Collector tests should feed representative CRI plain text,
multiline exception and JSON records and assert parsing, enrichment, redaction,
label allowlisting and malformed-line fallback.

## Failure modes and rollback

| Failure | Expected behavior and response |
|---|---|
| Loki/Tempo unavailable | Application traffic continues; bounded queues retry with exponential backoff then drop telemetry rather than block requests. Alert on drops. |
| Collector unavailable | SDK batches are bounded and non-blocking; stdout remains available to the container runtime. Restore collector before changing the app. |
| Object storage slow/unavailable | Ingesters use bounded WAL/persistence where supported; alert before capacity is exhausted. Do not switch to unreviewed local durability. |
| Malformed/multiline log | Route to a low-cardinality `parse_error` path with original body subject to size/redaction limits; alert on rate, never create labels from content. |
| Cardinality explosion | Tenant limits reject new streams; remove the offending label and replay only if privacy/cost permits. |
| Trace/log link absent | Search by request ID/time/service, then check span validity, JSON parsing, sampling, clock skew and data-source derived-field regex. |
| Duplicate telemetry | Compare SDK and collector exporters, disable exactly one path, and verify volume/cost returns to baseline. |
| Sensitive data detected | Restrict access, stop affected pipeline, preserve only access audit metadata, follow incident/privacy handling, fix source and processor, then validate deletion against retention/compaction behavior. |

Rollback is GitOps reversal: first return application trace export to the known
Application Insights configuration, then remove Grafana data-source references,
collector routing and backend Applications in dependency order. Retain storage
for the approved retention/incident window; infrastructure deletion is a
separate destructive change. Never use live Helm edits or delete storage as a
first response.

## Acceptance and activation gates

In staging, generate a request with a known valid `traceparent` and
`X-Request-ID`; verify the response ID, one privacy-safe Loki event, a matching
Tempo trace, and bidirectional Grafana links. Verify errors and slow traces meet
sampling policy, probes are excluded, malformed logs are bounded, and a canary
secret/PII marker is absent. Disconnect each backend and the collector in turn;
the request path must remain healthy and telemetry-loss alerts must fire.

Run a load test at forecast peak plus headroom and record ingestion loss, memory,
queue depth, stream count and query p95. Confirm restoration from object storage,
retention deletion, RBAC, network isolation, dashboards, alerts, runbook ownership
and monthly cost estimate. Only then schedule a reversible production canary.
No activation or deployment is authorised by this document.
