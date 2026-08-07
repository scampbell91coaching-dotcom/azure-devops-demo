from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SECRET = "flask-runtime-secrets"
MIGRATION_SECRET = "flask-migration-secrets"


def _documents(text: str) -> list[dict]:
    return [document for document in yaml.safe_load_all(text) if document]


def _database_secret(container: dict) -> str:
    database = next(item for item in container["env"] if item["name"] == "DATABASE_URL")
    return database["valueFrom"]["secretKeyRef"]["name"]


def test_production_helm_separates_runtime_and_migration_database_secrets():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "flask-web-prod",
            str(ROOT / "flask-app"),
            "--namespace",
            "production",
            "-f",
            str(ROOT / "flask-app/values-production.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = _documents(rendered)
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    migration = next(item for item in documents if item["kind"] == "Job")

    assert _database_secret(deployment["spec"]["template"]["spec"]["containers"][0]) == RUNTIME_SECRET
    assert _database_secret(migration["spec"]["template"]["spec"]["containers"][0]) == MIGRATION_SECRET
    assert MIGRATION_SECRET not in yaml.safe_dump(deployment)


def test_external_secrets_map_distinct_key_vault_database_urls():
    documents = _documents(
        (ROOT / "kubernetes/external-secrets/azure-key-vault.yaml").read_text()
    )
    external_secrets = {
        item["metadata"]["name"]: item
        for item in documents
        if item["kind"] == "ExternalSecret"
    }

    def remote_database_key(secret_name: str) -> str:
        data = external_secrets[secret_name]["spec"]["data"]
        entry = next(item for item in data if item["secretKey"] == "DATABASE_URL")
        return entry["remoteRef"]["key"]

    assert remote_database_key(RUNTIME_SECRET) == "database-runtime-url"
    assert remote_database_key(MIGRATION_SECRET) == "database-url"

    gitops = yaml.safe_load(
        (ROOT / "argocd-applications/external-secrets-production.yaml").read_text()
    )
    assert gitops["spec"]["source"]["path"] == "kubernetes/external-secrets"


def test_private_portal_runtime_pod_never_references_migration_secret():
    documents = _documents(
        (ROOT / "private-platform-manifests/private-platform.yaml").read_text()
    )
    deployment = next(
        item
        for item in documents
        if item["kind"] == "Deployment"
        and item["metadata"]["name"] == "platform-portal-private"
    )
    migration = next(item for item in documents if item["kind"] == "Job")

    pod_spec = deployment["spec"]["template"]["spec"]
    assert "initContainers" not in pod_spec
    assert _database_secret(pod_spec["containers"][0]) == RUNTIME_SECRET
    assert MIGRATION_SECRET not in yaml.safe_dump(deployment)
    assert _database_secret(migration["spec"]["template"]["spec"]["containers"][0]) == MIGRATION_SECRET
    assert RUNTIME_SECRET not in yaml.safe_dump(
        next(
            item
            for item in migration["spec"]["template"]["spec"]["containers"][0]["env"]
            if item["name"] == "DATABASE_URL"
        )
    )
