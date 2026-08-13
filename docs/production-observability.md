# Traditional Strength production observability

This document distinguishes the current production portal from repository-only
reference instrumentation and future observability work. Nothing described here
was deployed and no live alert was created.

The measurable paid-beta objectives, skip evidence requirements and alert
severities are defined in
[paid-beta-slos-and-python-skips.md](paid-beta-slos-and-python-skips.md).

## Current versus proposed

| Resource | Repository state | Runtime state |
|---|---|---|
| `platform-portal` on port 8090 | Existing | Current production image and `app:app` entry point |
| `/health` startup/readiness/liveness probes | Existing | Configured by the production Helm values |
| Portal `/metrics` and application telemetry | Future | The production portal does not currently expose `/metrics` or configure OpenTelemetry |
| Root `app/app.py` instrumentation | Reference only | Demo service on port 5000; not the production workload |
| `ServiceMonitor` | Repository template | Disabled unless both monitoring flags are explicitly enabled; do not enable before portal metrics exist |
| kube-prometheus-stack values | Existing | Confirm actual cluster state separately |
| Grafana production dashboard ConfigMap | Added | **Proposed; disabled** (`monitoring.enabled: false`) |
| Prometheus alert rules | Added | **Proposed; disabled** (`monitoring.enabled: false`) |
| Application Insights KQL alerts | Added as definitions | **Proposed text only; not live Azure resources** |
| Public Application Insights availability test | Design below | **Proposed; not provisioned** |

`monitoring.enabled` and `monitoring.serviceMonitor.enabled` are deliberately
false in both values files. A `ServiceMonitor` renders only when both are true.
The rule and dashboard have their own nested enablement under the main monitoring
switch. Network policy must also set `networkPolicy.allowMonitoring=true` before
Prometheus can reach the pod;
notification delivery additionally needs a separately reviewed Alertmanager
receiver and route. Never commit receiver tokens, webhooks, connection strings
or database credentials.

The root reference service exports `flask_http_requests_total`,
`flask_http_request_duration_seconds`, `flask_http_request_errors_total`, and
`flask_application_operations_total`. Labels are limited to HTTP method, Flask
route template, status code, and fixed operation/outcome values. Raw paths,
query strings, user identifiers, and other personal data are not labels.
Prometheus scrapes are excluded from its request metrics. These metrics and its
`/ready` and `/metrics` routes are not claims about the production portal.

## Coverage and practical starting thresholds

These older resource-oriented thresholds are implementation guidance. Where a
threshold differs, the paid-beta contract linked above is authoritative.

| Signal | Source | Proposed threshold |
|---|---|---|
| Private reachability after portal metrics work | Prometheus `up` over ClusterIP | below 1 for 5m; critical |
| Ready replicas | kube-state-metrics | available below desired for 10m; critical |
| Public `/health` | Application Insights availability | every 2m from 2+ locations; failure or missing checks for 5m; critical |
| HTTP 5xx after portal instrumentation | Prometheus / App Insights | over 5% for 10m, gated by >0.1 req/s or 20 requests; critical |
| HTTP latency after portal instrumentation | Prometheus / App Insights | p95 over 1s for 15m, 20-request gate in App Insights; warning |
| Pod restarts | kube-state-metrics | 3 in 15m, sustained for 5m; warning |
| Rollout | kube-state-metrics | `Progressing=false` for 10m; critical |
| Migration Job | kube-state-metrics | any failed Job matching `.*migrat.*` for 1m; critical |
| Worker/batch | kube-state-metrics / exceptions | failed named Job for 5m or 5 exceptions in 10m; warning |
| PostgreSQL | OpenTelemetry dependencies | 3 failed SQL/PostgreSQL calls from at least 5 in 10m; critical |
| CPU | container/kube-state metrics | over 85% of limit for 15m; warning |
| Memory | container/kube-state metrics | over 90% of limit for 10m; warning |

These are noise-resistant starting points. Review them after two weeks of normal
traffic. Absence of PostgreSQL dependency telemetry is not proof of health:
confirm that the database-using workload exports OpenTelemetry before activation.

## Ownership and dashboard

Platform owns dashboard availability, scraping, Kubernetes/resource alerts and
this runbook. Application owns HTTP, PostgreSQL, migration, worker and Job
diagnosis. Platform on-call triages first, then hands off when infrastructure is
healthy but application telemetry is failing.

The Grafana source is
`flask-app/dashboards/traditional-strength-production.json`. It links to
Application Insights for public availability, dependencies and traces instead of
copying Azure telemetry into Grafana. Alert metadata includes `owner`, `service`,
`severity` and `runbook_url`.

Before opt-in, verify the dashboard repository link, Grafana sidecar label,
PrometheusRule selector (`release: monitoring`), metric labels and Alertmanager
routing in a non-production environment.

## Public and private health

The proposed Application Insights **Standard availability test** targets
`https://traditionalstrength.co.uk/health`, requires HTTPS and status 200,
validates certificates and redirects, runs every two minutes from at least two
Azure locations, and is named `traditional-strength-public-health` for the KQL
definition in `kubernetes/monitoring/application-insights-alerts.kql`.

The current production portal exposes `/health`; Kubernetes startup, readiness,
and liveness all use that route on container port 8090. It does not expose
`/ready` or `/metrics`. A future private `/metrics` scrape could prove private
DNS, Service selection, endpoints, and pod HTTP reachability, but it requires
portal instrumentation first. Do not expose metrics publicly or add another
public load balancer.

```bash
curl -fsS --max-time 5 https://traditionalstrength.co.uk/health
kubectl run health-check --rm -i --restart=Never -n production \
  --image=curlimages/curl -- curl -fsS --max-time 5 \
  http://flask-web-prod-flask-app.production.svc.cluster.local/health
```

## Web unavailable or not Ready

```bash
kubectl get deploy,pod,endpointslice -n production -l app=flask-web
kubectl describe deployment flask-web -n production
kubectl get events -n production --sort-by=.lastTimestamp | tail -40
kubectl logs -n production -l app=flask-web --all-containers --tail=200
```

Public-only failure suggests DNS, TLS or ingress. Public and private failure with
healthy pods suggests Service selectors or policy. Never capture Secret values.

## HTTP errors or latency

Use the dashboard to identify status and onset, then Application Insights
transaction search to correlate requests, exceptions and dependencies. Compare
the deployment revision. If a release is causal, use the GitOps rollback in
`docs/runbook.md`; do not make an untracked live edit.

## Pod restarts or rollout failure

```bash
kubectl rollout status deployment/flask-web -n production --timeout=5m
kubectl describe pod -n production -l app=flask-web
kubectl logs -n production -l app=flask-web --previous --tail=200
kubectl get rs -n production -l app=flask-web
```

Check probes, OOMKilled, pulls, scheduling and missing secret references.

## PostgreSQL connectivity

Filter failed SQL dependencies in Application Insights by target/result and
correlate operation IDs. Confirm network policy, private DNS, TLS, server state
and ExternalSecret readiness without printing `DATABASE_URL`:

```bash
kubectl get networkpolicy,externalsecret -n production
az postgres flexible-server show --resource-group <resource-group> \
  --name <server> --query '{state:state,fqdn:fullyQualifiedDomainName}' -o table
```

## Migration Job failure

```bash
kubectl get jobs,pods -n production --sort-by=.metadata.creationTimestamp
kubectl describe job -n production <migration-job>
kubectl logs -n production job/<migration-job> --all-containers --tail=200
```

Stop rollout when schema compatibility is uncertain. Preserve sanitized logs,
image digest and migration version. Do not blindly rerun a non-idempotent job.

## Worker or Job failure

```bash
kubectl get job,cronjob,pod -n production
kubectl describe job -n production <job>
kubectl logs -n production job/<job> --all-containers --tail=200
```

Check backoff exhaustion, deadlines, missed schedules and correlated exceptions.
Jobs must include `traditional-strength`, `flask`, `worker`, or `migrat` in their
name for the proposed generic rules to select them.

## Resource pressure

```bash
kubectl top pod -n production -l app=flask-web --containers
kubectl describe pod -n production -l app=flask-web
kubectl get hpa -n production -o wide
```

Check throttling, OOM events, node pressure, HPA state and request/limit fit.
Change resources through reviewed Helm values, never a lasting live patch.

## Validation and activation gate

The validation is local and does not contact a cluster:

```bash
scripts/validate-observability.sh
```

Before setting either ServiceMonitor flag, add and test portal metrics, then
require owner and rule-expression review against real labels, staging
render/apply, monitoring NetworkPolicy ingress, Alertmanager route review, and
confirmation that public availability and PostgreSQL dependency telemetry exist.
Activation and deployment are outside this change.
