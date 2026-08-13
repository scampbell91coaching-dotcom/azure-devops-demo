from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).parents[1] / "postgres_migration_proof.py"
SPEC = importlib.util.spec_from_file_location("postgres_migration_proof", MODULE_PATH)
assert SPEC and SPEC.loader
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


def test_repository_has_one_canonical_head_and_exact_tail_chain():
    result = proof.migration_graph()

    assert result["ok"] is True
    assert result["heads"] == ["0023_organisation_invitation_delivery"]
    assert [(item["from"], item["to"]) for item in result["transitions"]] == list(
        zip(proof.EXPECTED_CHAIN, proof.EXPECTED_CHAIN[1:])
    )


def test_database_proof_rejects_non_postgresql_urls_before_connecting():
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        proof.database_proof("sqlite:///:memory:")


def test_default_run_does_not_fall_back_to_database_url(monkeypatch, capsys):
    monkeypatch.delenv("POSTGRES_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://must-not-be-used/production")

    assert proof.main([]) == 0
    assert '"status": "skipped"' in capsys.readouterr().out


def test_require_postgres_fails_closed_when_test_url_is_absent(monkeypatch):
    monkeypatch.delenv("POSTGRES_TEST_DATABASE_URL", raising=False)

    assert proof.main(["--require-postgres"]) == 1
