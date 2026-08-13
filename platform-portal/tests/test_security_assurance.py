"""Stable, repository-only contracts supporting the PL SaaS threat model.

These checks deliberately avoid asserting the active tenancy implementation.
Cross-tenant behavior remains covered by ``test_cross_tenant_security.py``.
"""

from pathlib import Path

import pytest

from portal import create_app
from portal.auth import _safe_redirect_target
from portal.models.organisation import (
    CoachAthleteOwnership,
    OrganisationMembership,
)


ROOT = Path(__file__).resolve().parents[2]
THREAT_MODEL = ROOT / "docs/security/pl-saas-threat-model.md"


def test_threat_model_keeps_every_release_blocker_machine_visible():
    text = THREAT_MODEL.read_text(encoding="utf-8")

    for blocker in ("RB-01", "RB-02", "RB-03", "RB-04", "RB-05", "RB-06"):
        assert text.count(f"| {blocker} |") == 1
    for threat in range(1, 13):
        assert text.count(f"| TM-{threat:02d} |") == 1


def test_production_auth_configuration_fails_closed_and_sets_cookie_contract(
    monkeypatch,
):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
        create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    app = create_app(
        {
            "SECRET_KEY": "assurance-only-configured-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    assert app.config["AUTHENTICATION_DISABLED"] is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


@pytest.mark.parametrize(
    "target",
    (
        "//attacker.example/path",
        "/%2f%2fattacker.example/path",
        "/%252f%252fattacker.example/path",
        "/%255cattacker.example/path",
        "/%0d%0aLocation:%20https://attacker.example",
    ),
)
def test_redirect_boundary_rejects_authority_confusion_and_encoded_controls(target):
    assert _safe_redirect_target(target) is False


def test_security_model_tracks_canonical_tenancy_and_remaining_storage_gap():
    model = THREAT_MODEL.read_text(encoding="utf-8")

    membership_columns = set(OrganisationMembership.__table__.columns.keys())
    ownership_columns = set(CoachAthleteOwnership.__table__.columns.keys())

    assert {"organisation_id", "user_id", "role", "status"} <= membership_columns
    assert {
        "organisation_id",
        "coach_membership_id",
        "athlete_id",
        "status",
    } <= ownership_columns
    assert "OrganisationMembership" in model
    assert "CoachAthleteOwnership" in model
    assert "not releasable as a multi-tenant SaaS" in model
    assert "PostgreSQL row-level enforcement is not yet evidenced" in model
