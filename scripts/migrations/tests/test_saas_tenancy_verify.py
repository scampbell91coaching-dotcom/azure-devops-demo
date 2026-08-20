from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "saas_tenancy_verify.py"
SPEC = importlib.util.spec_from_file_location("saas_tenancy_verify", MODULE_PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


def test_identifier_quoting_is_safe_for_catalog_values():
    assert verify._ident('training_sessions') == '"training_sessions"'
    assert verify._ident('bad"name') == '"bad""name"'


def test_rollout_phases_are_ordered_and_explicit():
    assert verify.PHASES == ("expand", "backfill", "constrain")
    assert verify.EXPECTED_HEAD == "0027_tenancy_ownership_expand"
    assert "organisations" in verify.CONTROL_TABLES
    assert "organisation_memberships" in verify.CONTROL_TABLES
    assert "coach_athlete_ownerships" in verify.CONTROL_TABLES
    assert "organisation_invitations" in verify.CONTROL_TABLES
    assert "organizations" in verify.REMOVED_TABLES


def test_verifier_source_enforces_read_only_transaction():
    source = MODULE_PATH.read_text()
    assert "SET TRANSACTION READ ONLY" in source
    assert "UPDATE " not in source
    assert "DELETE " not in source
    assert "INSERT " not in source
    assert "alembic_version SET" not in source
    assert '"transaction_is_read_only"' in source
    assert '"SHOW transaction_read_only"' in source
