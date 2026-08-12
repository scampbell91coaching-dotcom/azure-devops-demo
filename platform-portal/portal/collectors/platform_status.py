from __future__ import annotations

import argparse
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class CollectionError(RuntimeError):
    pass


class KubernetesClient:
    def __init__(self, api_url=None, token_file=None, ca_file=None, timeout=5):
        self.api_url = (api_url or os.getenv("KUBERNETES_SERVICE_HOST_URL") or "https://kubernetes.default.svc").rstrip("/")
        self.token_file = Path(token_file or "/var/run/secrets/kubernetes.io/serviceaccount/token")
        self.ca_file = Path(ca_file or "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        self.timeout = timeout

    def get(self, path: str) -> dict[str, Any]:
        token = self.token_file.read_text(encoding="utf-8").strip()
        request = urllib.request.Request(
            f"{self.api_url}{path}", headers={"Authorization": f"Bearer {token}"}
        )
        context = ssl.create_default_context(cafile=str(self.ca_file))
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:
                payload = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise CollectionError(f"Kubernetes GET {path} failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise CollectionError(f"Kubernetes GET {path} returned a non-object")
        return payload


def _items(client: KubernetesClient, path: str) -> list[dict[str, Any]]:
    value = client.get(path).get("items", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _condition(item: dict[str, Any], condition_type: str) -> bool | None:
    conditions = item.get("status", {}).get("conditions", [])
    for condition in conditions if isinstance(conditions, list) else []:
        if condition.get("type") == condition_type:
            return condition.get("status") == "True"
    return None


def _check(area: str, name: str, state: bool | None, detail: str, warn=False) -> dict[str, str]:
    status = "PASS" if state is True else "UNKNOWN" if state is None else ("WARN" if warn else "FAIL")
    return {"area": area, "name": name, "status": status, "detail": detail}


def _health(url: str, timeout: float) -> tuple[str | None, float | None]:
    import time

    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return str(response.status), round(time.monotonic() - started, 4)
    except urllib.error.HTTPError as exc:
        return str(exc.code), round(time.monotonic() - started, 4)
    except (OSError, urllib.error.URLError):
        return None, None


def database_migration_head(database_url: str | None) -> str | None:
    """Read Alembic's deployed head without changing database state."""
    if not database_url:
        return None
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            heads = [
                str(row[0])
                for row in connection.execute(
                    text(
                        "SELECT version_num FROM alembic_version ORDER BY version_num"
                    )
                )
            ]
    except (OSError, SQLAlchemyError):
        return None
    finally:
        engine.dispose()
    return ", ".join(heads) if heads else None


def collect(
    client: KubernetesClient,
    *,
    namespace: str,
    deployment_name: str,
    app_label: str,
    service_name: str,
    ingress_name: str,
    argo_namespace: str,
    argo_app: str,
    health_url: str,
    health_timeout: float = 5,
    migration_head: str | None = None,
) -> dict[str, Any]:
    quoted_label = urllib.parse.quote(f"app={app_label}")
    nodes = _items(client, "/api/v1/nodes")
    deployment = client.get(f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment_name}")
    pods = _items(client, f"/api/v1/namespaces/{namespace}/pods?labelSelector={quoted_label}")
    service = client.get(f"/api/v1/namespaces/{namespace}/services/{service_name}")
    client.get(f"/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{ingress_name}")
    network_policies = _items(client, f"/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies")
    argo = client.get(f"/apis/argoproj.io/v1alpha1/namespaces/{argo_namespace}/applications/{argo_app}")

    desired = int(deployment.get("spec", {}).get("replicas") or 0)
    ready = int(deployment.get("status", {}).get("readyReplicas") or 0)
    restarts = sum(
        int(status.get("restartCount") or 0)
        for pod in pods
        for status in pod.get("status", {}).get("containerStatuses", [])
        if isinstance(status, dict)
    )
    ready_nodes = sum(_condition(node, "Ready") is True for node in nodes)
    template_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    containers = template_spec.get("containers", [])
    container_security = [c.get("securityContext", {}) for c in containers if isinstance(c, dict)]
    pod_security = template_spec.get("securityContext", {})
    run_as_non_root = pod_security.get("runAsNonRoot") is True
    no_privilege = bool(container_security) and all(c.get("allowPrivilegeEscalation") is False for c in container_security)
    seccomp = pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"
    startup_probe = bool(containers) and all("startupProbe" in c for c in containers)
    http_code, latency = _health(health_url, health_timeout)
    argo_sync = argo.get("status", {}).get("sync", {}).get("status")
    argo_health = argo.get("status", {}).get("health", {}).get("status")
    argo_revision = argo.get("status", {}).get("sync", {}).get("revision")
    images = [
        str(container.get("image"))
        for container in containers
        if isinstance(container, dict) and container.get("image")
    ]
    deployed_image = ", ".join(images) if images else None

    metrics_available: bool | None
    try:
        _items(client, f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods")
        metrics_available = True
    except CollectionError:
        metrics_available = False
    try:
        monitors = _items(client, f"/apis/monitoring.coreos.com/v1/namespaces/{namespace}/servicemonitors")
        monitor_present: bool | None = bool(monitors)
    except CollectionError:
        monitor_present = None

    checks = [
        _check("Platform", "Kubernetes API", True, "Reachable"),
        _check("AKS", "Node readiness", bool(nodes) and ready_nodes == len(nodes), f"{ready_nodes}/{len(nodes)} Ready"),
        _check("Workload", "Deployment readiness", desired > 0 and ready == desired, f"{ready}/{desired} Ready"),
        _check("Workload", "Container restarts", restarts == 0, f"{restarts} restarts", warn=True),
        _check("Networking", "Service exposure", service.get("spec", {}).get("type") == "ClusterIP", str(service.get("spec", {}).get("type") or "unknown"), warn=True),
        _check("Networking", "Ingress", True, "Configured"),
        _check("Networking", "Network policies", bool(network_policies), f"{len(network_policies)} policies"),
        _check("Availability", "Public health", http_code == "200" if http_code else False, f"HTTP {http_code or 'unavailable'}"),
        _check("Performance", "Health latency", latency < 0.5 if latency is not None else False, f"{latency:.3f}s" if latency is not None else "Unavailable", warn=True),
        _check("Reliability", "Startup probe", startup_probe, "Configured" if startup_probe else "Missing", warn=True),
        _check("GitOps", "Argo CD", argo_sync == "Synced" and argo_health == "Healthy", f"{argo_sync or 'unknown'} / {argo_health or 'unknown'}", warn=True),
        _check("Security", "Non-root execution", run_as_non_root, "Enforced" if run_as_non_root else "Not detected", warn=True),
        _check("Security", "Privilege escalation", no_privilege, "Disabled" if no_privilege else "Not detected", warn=True),
        _check("Security", "Seccomp", seccomp, "RuntimeDefault" if seccomp else "Not detected", warn=True),
        _check("Observability", "Metrics API", metrics_available, "Available" if metrics_available else "Unavailable", warn=True),
        _check("Observability", "ServiceMonitor", monitor_present, "Present" if monitor_present else "Missing" if monitor_present is False else "Not reported", warn=True),
    ]
    weights = {"PASS": 100, "WARN": 50, "FAIL": 0, "UNKNOWN": 0}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": {"kubernetes_api": True, "nodes_ready": ready_nodes, "nodes_total": len(nodes)},
        "workload": {"ready_replicas": ready, "desired_replicas": desired, "container_restarts": restarts, "deployed_image": deployed_image},
        "networking": {"service_type": service.get("spec", {}).get("type"), "ingress_exists": True, "network_policy_count": len(network_policies)},
        "availability": {"http_code": http_code, "health_latency_seconds": latency},
        "gitops": {"sync_status": argo_sync, "health_status": argo_health, "revision": argo_revision},
        "database": {"migration_head": migration_head},
        "security": {"run_as_non_root": run_as_non_root, "privilege_escalation_disabled": no_privilege, "seccomp_runtime_default": seccomp},
        "observability": {"metrics_api_available": metrics_available, "service_monitor_present": monitor_present},
        "checks": checks,
        "score": round(sum(weights[c["status"]] for c in checks) / len(checks)),
        "summary": {name.lower(): sum(c["status"] == name for c in checks) for name in ("PASS", "WARN", "FAIL")},
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sample_snapshot(generated_at: str = "2026-08-09T12:00:00+00:00") -> dict[str, Any]:
    """Deterministic local-only fixture; values are explicitly synthetic."""
    checks = [
        _check("Platform", "Kubernetes API", True, "Synthetic local fixture"),
        _check("Workload", "Deployment readiness", True, "2/2 Ready"),
        _check("GitOps", "Argo CD", False, "OutOfSync / Degraded", warn=True),
        _check("Observability", "Metrics API", True, "Available"),
    ]
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "platform": {"kubernetes_api": True, "nodes_ready": 2, "nodes_total": 2},
        "workload": {"ready_replicas": 2, "desired_replicas": 2, "container_restarts": 0, "deployed_image": "registry.example/traditional-strength@sha256:synthetic"},
        "availability": {"http_code": "200", "health_latency_seconds": 0.125},
        "gitops": {"sync_status": "OutOfSync", "health_status": "Degraded", "revision": "synthetic-revision"},
        "database": {"migration_head": "synthetic-head"},
        "observability": {"metrics_api_available": True, "service_monitor_present": False},
        "checks": checks,
        "score": 88,
        "summary": {"pass": 3, "warn": 1, "fail": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.getenv("PLATFORM_STATUS_OUTPUT", "/status/platform-status.json"))
    parser.add_argument("--sample", action="store_true", help="write the documented synthetic local fixture")
    parser.add_argument("--sample-state", choices=("current", "stale"), default="current")
    args = parser.parse_args()
    if args.sample:
        generated = datetime.now(timezone.utc)
        if args.sample_state == "stale":
            generated -= timedelta(minutes=16)
        payload = sample_snapshot(generated.isoformat())
    else:
        required = ("STATUS_NAMESPACE", "STATUS_DEPLOYMENT", "STATUS_APP_LABEL", "STATUS_SERVICE", "STATUS_INGRESS", "STATUS_ARGO_APP", "STATUS_HEALTH_URL")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise SystemExit(f"Missing collector configuration: {', '.join(missing)}")
        payload = collect(
            KubernetesClient(timeout=float(os.getenv("STATUS_API_TIMEOUT_SECONDS", "5"))),
            namespace=os.environ["STATUS_NAMESPACE"], deployment_name=os.environ["STATUS_DEPLOYMENT"],
            app_label=os.environ["STATUS_APP_LABEL"], service_name=os.environ["STATUS_SERVICE"],
            ingress_name=os.environ["STATUS_INGRESS"], argo_namespace=os.getenv("STATUS_ARGO_NAMESPACE", "argocd"),
            argo_app=os.environ["STATUS_ARGO_APP"], health_url=os.environ["STATUS_HEALTH_URL"],
            health_timeout=float(os.getenv("STATUS_HEALTH_TIMEOUT_SECONDS", "5")),
            migration_head=database_migration_head(os.getenv("DATABASE_URL")),
        )
    atomic_write(Path(args.output), payload)
    print(f"Wrote status snapshot to {args.output}")


if __name__ == "__main__":
    main()
