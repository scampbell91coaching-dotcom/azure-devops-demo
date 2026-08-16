from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).parents[1]


def _render(*extra: str):
    result = subprocess.run(
        ["helm", "template", "flask-web-prod", str(ROOT / "flask-app"),
         "--namespace", "production", "-f", str(ROOT / "flask-app/values-production.yaml"), *extra],
        check=True, capture_output=True, text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def test_pinned_release_uses_only_the_shared_health_contract_without_image_drift():
    documents = _render()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].endswith(":3c19fbb7473d8281415fbc4fa848a00ea04bd9ec")
    assert {container[name]["httpGet"]["path"] for name in
            ("startupProbe", "readinessProbe", "livenessProbe")} == {"/health"}
    assert "METRICS_BEARER_TOKEN" not in {item["name"] for item in container["env"]}


def test_public_ingress_has_no_metrics_path_and_internal_scrape_uses_a_secret():
    documents = _render("--set", "monitoring.enabled=true",
                        "--set", "monitoring.serviceMonitor.enabled=true",
                        "--set", "networkPolicy.allowMonitoring=true")
    ingress = next(item for item in documents if item["kind"] == "Ingress")
    assert all(path["path"] != "/metrics" for rule in ingress["spec"]["rules"]
               for path in rule["http"]["paths"])
    assert "^/metrics" in ingress["metadata"]["annotations"][
        "nginx.ingress.kubernetes.io/configuration-snippet"
    ]
    monitor = next(item for item in documents if item["kind"] == "ServiceMonitor")
    endpoint = monitor["spec"]["endpoints"][0]
    assert endpoint["path"] == "/metrics"
    assert endpoint["authorization"]["credentials"] == {
        "name": "flask-runtime-secrets", "key": "METRICS_BEARER_TOKEN"
    }
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    env_names = {item["name"] for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert "METRICS_BEARER_TOKEN" in env_names
    policy = next(item for item in documents if item["kind"] == "NetworkPolicy" and
                  item["metadata"]["name"].endswith("allow-required"))
    namespaces = [source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"]
                  for rule in policy["spec"]["ingress"] for source in rule["from"]]
    assert "monitoring" in namespaces


def test_alert_promql_covers_absence_degraded_and_only_current_app_migration():
    documents = _render("--set", "monitoring.enabled=true")
    rule = next(item for item in documents if item["kind"] == "PrometheusRule")
    alerts = {entry["alert"]: entry["expr"] for group in rule["spec"]["groups"]
              for entry in group["rules"]}
    assert "absent(traditional_strength_dependency_available" in alerts["TraditionalStrengthDatabaseUnavailable"]
    argo = alerts["TraditionalStrengthArgoReleaseDegraded"]
    assert 'health_status=~"Degraded|Missing"' in argo and "sync_status" not in argo
    migration = alerts["TraditionalStrengthMigrationJobFailed"]
    assert 'job_name="flask-web-prod-flask-app-migration"' in migration
    assert "kube_job_labels" in migration
    assert 'label_app_kubernetes_io_component="migration"' in migration
    assert ".*migrat.*" not in migration
    assert "< 900" in migration
    page = alerts["TraditionalStrengthHttp5xxPage"]
    assert "increase(" in page and ">= 5" in page and ">= 20" in page
