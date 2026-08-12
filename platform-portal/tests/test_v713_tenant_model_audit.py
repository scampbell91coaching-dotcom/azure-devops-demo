"""Executable assertions for the V7.13 pre-tenant schema baseline.

These are diagnostics, not the desired SaaS end state. They make a future migration
explicit: when tenant ownership is added, update this audit and replace these assertions
with positive and negative two-tenant isolation tests.
"""

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

UNOWNED_BUSINESS_ROOTS = {
    "athletes",
    "coaching_applications",
    "lead_captures",
    "meets",
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
        tenant_columns = {
            table.name: column.name
            for table in db.metadata.tables.values()
            for column in table.columns
            if column.name in {"tenant_id", "organisation_id", "organization_id"}
        }
        assert {
            "organisation_memberships",
            "coach_athlete_ownerships",
            "membership_invitations",
            "subscription_accounts",
        } <= set(tenant_columns)


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


def test_v713_business_roots_cannot_express_tenant_ownership(app):
    with app.app_context():
        for table_name in UNOWNED_BUSINESS_ROOTS:
            table = db.metadata.tables[table_name]
            assert not any(
                foreign_key.target_fullname.startswith("tenants.")
                for column in table.columns
                for foreign_key in column.foreign_keys
            ), table_name


def test_meal_plan_assignment_template_link_is_not_database_enforced(app):
    """Capture the highest-risk existing relationship gap before migration."""
    with app.app_context():
        column = db.metadata.tables["meal_plan_assignments"].c.template_id
        assert not column.foreign_keys
