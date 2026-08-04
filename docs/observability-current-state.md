# Observability current state

**Audit date:** 2026-08-04
**Scope:** repository-only review; no cluster, Azure subscription, dashboard, or
secret access was performed

## Executive finding

The repository has useful observability building blocks, but the active
production path does not join them into a working end-to-end system. The
production workflow builds `platform-portal`, whose requirements and startup
code contain neither Prometheus nor Azure Monitor/OpenTelemetry
instrumentation. The Helm chart contains a disabled `ServiceMonitor` template
for a future `/metrics` endpoint and injects an Application Insights connection string. Production
NetworkPolicy also has `allowMonitoring: false`. Consequently, the presence of
the custom resource, secret reference, screenshots, or Terraform component is
not evidence that production metrics or traces are being collected.

The strongest implemented coverage is shallow process health, Kubernetes
probes, Gunicorn stdout/stderr logging, an Azure Log Analytics workspace,
workspace-based Application Insights, and AKS Container Insights wiring.
Dashboards and alert expressions exist as disabled or text-only proposals.
Loki and Tempo are future-work mentions only.

## Classification method

- **Implemented:** code and configuration are joined into the repository's
  production delivery path. This does not claim that a live deployment was
  inspected.
- **Partial:** useful pieces exist, but activation, application wiring,
  validation, or an operational dependency is missing.
- **Absent:** no functional implementation was found.
- **Intentionally deferred:** the repository explicitly marks the capability as
  proposed, disabled, or future work.

## Capability matrix

| Capability | Status | Repository evidence | Gap or qualification |
|---|---|---|---|
| Azure Monitor / Log Analytics | Partial | `infra/modules/monitoring/main.tf` creates a 30-day Log Analytics workspace and a Linux performance/syslog DCR. `infra/aks/main.tf` enables the AKS `oms_agent`. | The DCR has no association and is VM-oriented after VM infrastructure was removed. No diagnostic settings, ingestion cap, cost alert, Azure resource-health alert, or Azure Monitor alert resources are declared. Live ingestion was not checked. |
| Application Insights | Partial | Terraform creates a workspace-based component and exports its sensitive connection string. External Secrets maps the Key Vault secret and the production Deployment injects `APPLICATIONINSIGHTS_CONNECTION_STRING`. | The production image is built from `platform-portal`, whose requirements omit `azure-monitor-opentelemetry` and whose application factory never calls `configure_azure_monitor`. The instrumented `app/app.py` is a separate demo image, not the current production build context. Availability tests and scheduled-query alerts are text-only proposals. |
| OpenTelemetry | Partial | `app/app.py` conditionally calls the Azure Monitor OpenTelemetry distribution before importing Flask. | This code is outside the production build path. There is no SDK configuration in `platform-portal`, no Collector manifest, no OTLP endpoint, no sampling/resource policy, and no collector health or queue monitoring. |
| Prometheus application metrics | Intentionally deferred | The root demo `app/app.py` implements request counters, a latency histogram, application info, and `/metrics`; `flask-app/templates/servicemonitor.yaml` declares a future scrape. | The deployed `platform-portal` has no `/metrics` endpoint or `prometheus-client`. The `ServiceMonitor` requires both `monitoring.enabled=true` and `monitoring.serviceMonitor.enabled=true`, production monitoring ingress is disabled, and no successful production scrape is claimed. |
| Prometheus platform stack | Partial | `kubernetes/monitoring/values.yaml` supplies small-footprint values for Prometheus, Grafana, Alertmanager, and the operator. Repository screenshots show a stack existed at some point. | No pinned chart dependency, Helm release, Argo CD Application, install automation, storage, backup, authentication, or live inventory is in source control. Three-day ephemeral retention is configured. Screenshots do not establish current state. |
| Loki | Intentionally deferred | `README.md` lists Loki log aggregation under future improvements. | No Loki chart values, manifests, storage, retention, tenant/auth configuration, log agent, or Grafana data source exists. |
| Tempo / distributed tracing backend | Intentionally deferred | `README.md` lists Tempo and an OpenTelemetry Collector under future improvements. | No Tempo or Collector deployment, storage, receiver/exporter configuration, service graph, trace-to-log link, or Grafana data source exists. Application Insights is the stated trace destination, but production instrumentation is not wired. |
| Application logging | Partial | `platform-portal/Dockerfile` sends Gunicorn access and error logs to stdout/stderr; AKS is connected to Log Analytics. | Access logs are unstructured, application logging has no central policy, safe request/trace correlation, field schema, severity conventions, PII/secret redaction tests, retention query, or volume controls. Public image Gunicorn logging is not explicit. |
| Log aggregation | Partial | AKS Container Insights can collect container logs into Log Analytics, subject to live configuration. | No repository evidence proves collection/query health. Loki is absent, and there is no declared choice of one authoritative log store to prevent duplicate ingestion and cost. |
| Tracing | Absent | The non-production demo can enable Azure Monitor auto-instrumentation. | The production application has no trace provider/exporter or propagation verification. There are no span attributes, database-span validation, sampling rules, trace retention policy, or trace/log correlation tests. |
| Health endpoint | Implemented | `platform-portal/portal/api/health.py` returns a minimal 200 response; container and Helm health checks call `/health`; route tests cover the endpoint. | It proves only that Flask can answer. It does not report dependencies, build/version, or degraded state, which is appropriate for liveness but insufficient for readiness. |
| Startup, readiness, and liveness | Partial | The production Helm Deployment configures all three probes with timeouts and thresholds. | Every probe calls the same shallow endpoint. There is no dependency-aware readiness endpoint with a strict timeout, so a pod can be Ready while PostgreSQL is unavailable. |
| Grafana dashboards | Partial | A production health dashboard JSON and sidecar-labelled ConfigMap template exist; repository screenshots show generic Kubernetes dashboards. | `monitoring.enabled` is false in production. The stack/data source/sidecar are not declaratively installed, dashboard PromQL is not tested against real labels, and links use a broad Azure resource browser rather than a specific component. |
| Sanitised platform portal | Partial | The status collector checks Metrics API presence, `ServiceMonitor` presence, public health, and latency; the portal renders those fields. | Presence is not scrape health. It does not query Prometheus targets, Application Insights ingestion, alert state, log freshness, or trace export, and its snapshot can become stale. |
| Prometheus alert rules | Intentionally deferred | `flask-app/templates/prometheusrule.yaml` defines availability, readiness, HTTP, rollout, Job, CPU, memory, and restart rules. The local validation renders them when forced on. | Production values explicitly disable them. Expressions have not been validated against actual target and kube-state-metrics labels. No recording rules, SLO/burn-rate alerts, dead-man signal, inhibition, or notification path is configured. |
| Azure alerts and synthetic availability | Intentionally deferred | `kubernetes/monitoring/application-insights-alerts.kql` contains proposed KQL and `docs/production-observability.md` specifies a public test. | There are no Terraform availability-test, scheduled-query alert, metric alert, action group, or notification resources. The KQL is not executable provisioning. |
| Alertmanager and notifications | Intentionally deferred | The monitoring values size an Alertmanager workload. Documentation explicitly requires separate receiver and route review. | No receiver, route, inhibition, grouping, silences policy, delivery integration, ownership schedule, or end-to-end test exists. No secrets should be added to Git. |
| Operational dashboards and SLOs | Intentionally deferred | Proposed thresholds and a production health dashboard exist. `docs/limitations.md` states that formal SLOs and error budgets are not implemented. | No agreed SLI definitions, availability objective, error-budget calculation, burn-rate rules, or product/business telemetry is present. |
| Runbooks | Partial | `docs/runbook.md` covers deployment, ingress, rollback, and validation; `docs/production-observability.md` covers several proposed alert symptoms and includes safe diagnostic commands. | Runbooks are not tied to active notifications. They lack alert acknowledgement/escalation, severity policy, communications, Loki/Tempo procedures, telemetry-pipeline failure, dashboard/data-source failure, and post-incident follow-up. Some architecture and limitations text is stale relative to current Helm values. |
| Kubernetes/Helm manifests | Partial | Production health probes, an explicitly opt-in `ServiceMonitor`, proposed `PrometheusRule`, dashboard ConfigMap, monitoring NetworkPolicy option, and monitoring stack values exist. | Default and production renders omit the `ServiceMonitor`; it appears only when both monitoring flags are true. Production blocks scraper ingress and the portal has no scrape endpoint. No Loki, Tempo, Collector, data-source, persistence, or monitoring-stack GitOps manifests exist. |
| Terraform observability | Partial | A reusable monitoring module provisions Log Analytics and Application Insights; AKS references the workspace. | Names/tags are lab-specific and fixed. Missing resources include diagnostic settings, DCR association, availability tests, alerts, action groups, dashboards/workbooks, Managed Grafana, budgets/caps, and observability outputs other than the connection string. `infra/README.md` overstates Managed Grafana and alert provisioning. |

## Cross-cutting risks

1. **Premature metrics activation:** explicitly enabling the `ServiceMonitor`
   before portal instrumentation would target a missing `/metrics` route, while
   the status portal reports only object presence rather than scrape health.
2. **False confidence from configuration:** secret injection and an Application
   Insights resource do not make an uninstrumented application emit telemetry.
3. **No actionable alert path:** proposed rules cannot page an owner; there is no
   declarative receiver, routing policy, or tested delivery.
4. **Split and potentially duplicative backends:** Azure Monitor is partly
   adopted while Loki/Tempo are proposed without a documented signal-routing
   and retention decision.
5. **Sensitive-data exposure:** the coaching application handles personal data,
   but no structured logging/redaction contract or telemetry attribute allowlist
   is tested.
6. **Unverifiable runtime claims:** screenshots and narrative docs show historic
   or intended state. This audit deliberately makes no claim about live Azure or
   AKS resources.

## Immediate acceptance checks for future implementation

An observability capability should not be called implemented until a non-secret
test or deployment check proves its full path: producer, network, collector,
storage, query/dashboard, alert evaluation, notification delivery, and linked
runbook. Evidence should contain names, health, timestamps, and sanitized query
results only—never tokens, connection strings, log bodies containing user data,
or Terraform state.
