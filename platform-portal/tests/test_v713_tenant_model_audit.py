"""Executable assertions for the reconciled V7.13 canonical tenant schema."""

import pytest

from portal import create_app
from portal.extensions import db


ATHLETE_OWNED_TABLES = {
    "account_tokens",
    "athlete_checkin_settings",
    "athlete_constraint_flags",
    "athlete_state_facts",
    "athlete_state_overrides",
    "athlete_state_recommendations",
    "athlete_state_signals",
    "client_service_changes",
    "coach_technical_observations",
    "daily_nutrition",
    "external_coaching_reviews",
    "meal_plan_assignments",
    "meet_entries",
    "nutrition_checkins",
    "nutrition_import_jobs",
    "nutrition_macro_prescriptions",
    "nutrition_provider_connections",
    "programme_revisions",
    "training_blocks",
    "training_session_logs",
    "warmup_assignments",
    "warmup_overrides",
    "warmup_plan_snapshots",
    "weekly_checkins",
}

CANONICAL_TENANT_TABLES = {
    "organisations",
    "organisation_memberships",
    "coach_athlete_ownerships",
    "organisation_invitations",
}

REMOVED_SCHEMA_FAMILIES = {
    "organizations", "organization_memberships", "organization_athletes",
    "organization_invitations", "organization_onboarding", "memberships",
    "membership_invitations", "membership_invitation_audit", "organisation_athletes",
}


@pytest.fixture
def app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_v713_audit_gap_is_closed_by_integrated_tenant_schema(app):
    """Keep the audit executable while recognising the integrated SaaS foundation."""
    with app.app_context():
        assert "tenants" not in db.metadata.tables
        assert "tenant_memberships" not in db.metadata.tables
        assert CANONICAL_TENANT_TABLES <= set(db.metadata.tables)
        assert REMOVED_SCHEMA_FAMILIES.isdisjoint(db.metadata.tables)
        assert "organisation_id" in db.metadata.tables["subscription_accounts"].c


def test_v713_athlete_owned_rows_have_an_athlete_foreign_key(app):
    """Keep the current de-facto ownership graph visible and reviewable."""
    with app.app_context():
        for table_name in ATHLETE_OWNED_TABLES:
            table = db.metadata.tables[table_name]
            assert any(
                foreign_key.target_fullname == "athletes.id"
                for column in table.columns
                for foreign_key in column.foreign_keys
            ), table_name


def test_v713_ownership_edges_use_canonical_organisation_foreign_keys(app):
    with app.app_context():
        for table_name in CANONICAL_TENANT_TABLES - {"organisations"}:
            table = db.metadata.tables[table_name]
            assert "organisation_id" in table.c
            assert any(
                foreign_key.target_fullname == "organisations.id"
                for foreign_key in table.c.organisation_id.foreign_keys
            ), table_name


def test_meal_plan_assignment_template_link_is_not_database_enforced(app):
    """Capture the highest-risk existing relationship gap before migration."""
    with app.app_context():
        column = db.metadata.tables["meal_plan_assignments"].c.template_id
        assert not column.foreign_keys
