#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "azure-devops-demo").resolve()
OUT = REPO / "platform-portal" / "data" / "platform-status.json"
NAMESPACE = "production"
DEPLOYMENT = "flask-web"
SERVICE = "flask-web-prod-flask-app"
INGRESS = "flask-web-prod"
ARGO_APP = "flask-web-production"
URL = "https://traditionalstrength.co.uk/health"


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def run_ok(*args: str) -> bool:
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def kubectl_jsonpath(kind: str, name: str, namespace: str, path: str) -> str:
    return run("kubectl", "get", kind, name, "-n", namespace, "-o", f"jsonpath={path}")


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: str, default: float = 99.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def curl_metric(fmt: str) -> str:
    return run("curl", "-o", "/dev/null", "-sS", "-w", fmt, "--max-time", "10", URL)


def add_check(checks: list[dict[str, Any]], area: str, name: str, ok: bool, detail: str, warn: bool = False) -> None:
    checks.append({
        "area": area,
        "name": name,
        "status": "PASS" if ok else ("WARN" if warn else "FAIL"),
        "detail": detail,
    })


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    kubernetes_api = run_ok("kubectl", "cluster-info")

    nodes_raw = run("kubectl", "get", "nodes", "--no-headers")
    node_lines = [line for line in nodes_raw.splitlines() if line.strip()]
    nodes_total = len(node_lines)
    nodes_ready = sum(1 for line in node_lines if len(line.split()) > 1 and line.split()[1] == "Ready")

    ready_replicas = to_int(kubectl_jsonpath("deployment", DEPLOYMENT, NAMESPACE, "{.status.readyReplicas}"))
    desired_replicas = to_int(kubectl_jsonpath("deployment", DEPLOYMENT, NAMESPACE, "{.spec.replicas}"))

    restart_values = run(
        "kubectl", "get", "pods", "-n", NAMESPACE, "-l", "app=flask-web",
        "-o", "jsonpath={range .items[*]}{range .status.containerStatuses[*]}{.restartCount}{\"\\n\"}{end}{end}"
    )
    restarts = sum(to_int(v) for v in restart_values.splitlines() if v.strip())

    service_type = kubectl_jsonpath("service", SERVICE, NAMESPACE, "{.spec.type}") or "unknown"
    ingress_exists = run_ok("kubectl", "get", "ingress", INGRESS, "-n", NAMESPACE)

    network_policy_count = len([
        line for line in run("kubectl", "get", "networkpolicy", "-n", NAMESPACE, "--no-headers").splitlines()
        if line.strip()
    ])

    http_code = curl_metric("%{http_code}") or "000"
    health_latency = to_float(curl_metric("%{time_total}"))

    hpa_exists = bool(run("kubectl", "get", "hpa", "-n", NAMESPACE, "--no-headers"))
    pdb_exists = run_ok("kubectl", "get", "pdb", DEPLOYMENT, "-n", NAMESPACE)

    external_secret_ready = (
        kubectl_jsonpath(
            "externalsecret",
            "flask-runtime-secrets",
            NAMESPACE,
            '{.status.conditions[?(@.type=="Ready")].status}',
        ) == "True"
    )

    argo_sync = kubectl_jsonpath("application", ARGO_APP, "argocd", "{.status.sync.status}") or "unknown"
    argo_health = kubectl_jsonpath("application", ARGO_APP, "argocd", "{.status.health.status}") or "unknown"

    deployment_yaml = run("kubectl", "get", "deployment", DEPLOYMENT, "-n", NAMESPACE, "-o", "yaml")
    run_as_non_root = "runAsNonRoot: true" in deployment_yaml
    privilege_escalation_disabled = "allowPrivilegeEscalation: false" in deployment_yaml
    seccomp_runtime_default = "type: RuntimeDefault" in deployment_yaml
    startup_probe = "startupProbe:" in deployment_yaml
    topology_spread = "topologySpreadConstraints:" in deployment_yaml

    metrics_api = run_ok("kubectl", "top", "pods", "-n", NAMESPACE)
    service_monitor_present = bool(run("kubectl", "get", "servicemonitor", "-n", NAMESPACE, "--no-headers"))

    git_branch = run("git", "-C", str(REPO), "branch", "--show-current")
    git_revision = run("git", "-C", str(REPO), "rev-parse", "--short", "HEAD")
    git_clean = not bool(run("git", "-C", str(REPO), "status", "--porcelain"))
    last_commit_date = run("git", "-C", str(REPO), "log", "-1", "--format=%cI")
    last_commit_message = run("git", "-C", str(REPO), "log", "-1", "--format=%s")

    data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "kubernetes_api": kubernetes_api,
            "nodes_ready": nodes_ready,
            "nodes_total": nodes_total,
        },
        "workload": {
            "ready_replicas": ready_replicas,
            "desired_replicas": desired_replicas,
            "container_restarts": restarts,
        },
        "networking": {
            "service_type": service_type,
            "ingress_exists": ingress_exists,
            "network_policy_count": network_policy_count,
        },
        "availability": {
            "http_code": http_code,
            "health_latency_seconds": health_latency,
        },
        "resilience": {
            "hpa_exists": hpa_exists,
            "pdb_exists": pdb_exists,
            "startup_probe": startup_probe,
            "topology_spread": topology_spread,
        },
        "identity": {
            "external_secret_ready": external_secret_ready,
        },
        "gitops": {
            "sync_status": argo_sync,
            "health_status": argo_health,
        },
        "security": {
            "run_as_non_root": run_as_non_root,
            "privilege_escalation_disabled": privilege_escalation_disabled,
            "seccomp_runtime_default": seccomp_runtime_default,
        },
        "observability": {
            "metrics_api_available": metrics_api,
            "service_monitor_present": service_monitor_present,
        },
        "git": {
            "branch": git_branch,
            "revision": git_revision,
            "clean": git_clean,
            "last_commit_date": last_commit_date,
            "last_commit_message": last_commit_message,
        },
    }

    checks: list[dict[str, Any]] = []
    add_check(checks, "Platform", "Kubernetes API", kubernetes_api, "Reachable" if kubernetes_api else "Unreachable")
    add_check(checks, "AKS", "Node readiness", nodes_total > 0 and nodes_ready == nodes_total, f"{nodes_ready}/{nodes_total} Ready")
    add_check(checks, "Workload", "Deployment readiness", desired_replicas > 0 and ready_replicas == desired_replicas, f"{ready_replicas}/{desired_replicas} Ready")
    add_check(checks, "Workload", "Container restarts", restarts == 0, f"{restarts} restarts", warn=True)
    add_check(checks, "Networking", "Service exposure", service_type == "ClusterIP", service_type, warn=True)
    add_check(checks, "Networking", "Ingress", ingress_exists, "Configured" if ingress_exists else "Missing")
    add_check(checks, "Networking", "Network policies", network_policy_count > 0, f"{network_policy_count} policies")
    add_check(checks, "Availability", "Public health", http_code == "200", f"HTTP {http_code}")
    add_check(checks, "Performance", "Health latency", health_latency < 0.5, f"{health_latency:.3f}s", warn=True)
    add_check(checks, "Resilience", "Horizontal autoscaling", hpa_exists, "Configured" if hpa_exists else "Missing", warn=True)
    add_check(checks, "Resilience", "Pod disruption budget", pdb_exists, "Configured" if pdb_exists else "Missing", warn=True)
    add_check(checks, "Reliability", "Startup probe", startup_probe, "Configured" if startup_probe else "Missing", warn=True)
    add_check(checks, "Scheduling", "Topology spread", topology_spread, "Configured" if topology_spread else "Missing", warn=True)
    add_check(checks, "Identity", "External Secret", external_secret_ready, "Ready" if external_secret_ready else "Not Ready", warn=True)
    add_check(checks, "GitOps", "Argo CD", argo_sync == "Synced" and argo_health == "Healthy", f"{argo_sync} / {argo_health}", warn=True)
    add_check(checks, "Security", "Non-root execution", run_as_non_root, "Enforced" if run_as_non_root else "Not detected", warn=True)
    add_check(checks, "Security", "Privilege escalation", privilege_escalation_disabled, "Disabled" if privilege_escalation_disabled else "Not detected", warn=True)
    add_check(checks, "Security", "Seccomp", seccomp_runtime_default, "RuntimeDefault" if seccomp_runtime_default else "Not detected", warn=True)
    add_check(checks, "Observability", "Metrics API", metrics_api, "Available" if metrics_api else "Unavailable", warn=True)
    add_check(checks, "Observability", "ServiceMonitor", service_monitor_present, "Present" if service_monitor_present else "Missing", warn=True)
    add_check(checks, "Repository", "Working tree", git_clean, "Clean" if git_clean else "Local changes", warn=True)

    weights = {"PASS": 100, "WARN": 50, "FAIL": 0}
    data["checks"] = checks
    data["score"] = round(sum(weights[item["status"]] for item in checks) / len(checks))
    data["summary"] = {
        "pass": sum(item["status"] == "PASS" for item in checks),
        "warn": sum(item["status"] == "WARN" for item in checks),
        "fail": sum(item["status"] == "FAIL" for item in checks),
    }

    temp = OUT.with_suffix(".json.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    temp.replace(OUT)

    print(f"Wrote {OUT}")
    print(f"Score={data['score']} PASS={data['summary']['pass']} WARN={data['summary']['warn']} FAIL={data['summary']['fail']}")


if __name__ == "__main__":
    main()
