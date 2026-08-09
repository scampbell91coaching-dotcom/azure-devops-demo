from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def documents(name):
    return list(yaml.safe_load_all((ROOT / "private-platform-manifests" / name).read_text()))


def test_collector_rbac_is_read_only_and_cronjob_is_isolated():
    docs = documents("platform-status-collector.yaml")
    rules = [rule for doc in docs if doc and doc.get("kind") in {"Role", "ClusterRole"} for rule in doc.get("rules", [])]
    assert rules
    assert {verb for rule in rules for verb in rule["verbs"]} <= {"get", "list"}
    assert not ({"secrets", "events"} & {resource for rule in rules for resource in rule["resources"]})
    cron = next(doc for doc in docs if doc and doc.get("kind") == "CronJob")
    assert cron["spec"]["schedule"] == "*/5 * * * *"
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"
    assert cron["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] == 120


def test_portal_mounts_configured_snapshot_read_only():
    deployment = next(doc for doc in documents("private-platform.yaml") if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "platform-portal-private")
    portal = deployment["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item.get("value") for item in portal["env"]}
    mount = next(item for item in portal["volumeMounts"] if item["name"] == "platform-status")
    assert env["PLATFORM_STATUS_FILE"] == "/status/platform-status.json"
    assert env["PLATFORM_STATUS_FRESHNESS_SECONDS"] == "900"
    assert mount["readOnly"] is True
    assert deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
