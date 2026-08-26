"""Expand nullable organisation ownership and revocation structure.

Revision ID: 0027_tenancy_ownership_expand
Revises: 0026_programming_exposure_roles

This is an expand-only migration.  It deliberately does not populate tenant
keys, change existing nullability/uniqueness, or make the application consume
the new structure.  PostgreSQL foreign keys added to populated tables are NOT
VALID so installation does not scan or classify legacy data.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_tenancy_ownership_expand"
down_revision = "0026_programming_exposure_roles"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "athletes",
    "account_tokens",
    "client_service_changes",
    "athlete_checkin_settings",
    "weekly_checkins",
    "nutrition_checkins",
    "athlete_state_facts",
    "coach_technical_observations",
    "athlete_constraint_flags",
    "athlete_state_signals",
    "athlete_state_recommendations",
    "athlete_state_overrides",
    "external_coaching_reviews",
    "training_blocks",
    "programme_revisions",
    "training_weeks",
    "training_sessions",
    "programming_lift_slots",
    "exercise_prescriptions",
    "training_session_logs",
    "training_set_results",
    "nutrition_provider_connections",
    "nutrition_import_jobs",
    "daily_nutrition",
    "nutrition_macro_prescriptions",
    "meets",
    "meet_entries",
    "meet_lifts",
    "warmup_protocols",
    "warmup_protocol_steps",
    "warmup_assignments",
    "warmup_overrides",
    "warmup_plan_snapshots",
    "warmup_plan_snapshot_steps",
    "meal_plan_templates",
    "meal_plan_assignments",
)


def _add_nullable_fk(table, column, target, name):
    op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            name, table, target, [column], ["id"], ondelete="RESTRICT",
            postgresql_not_valid=True,
        )


def _create_index(name, table, columns, *, unique=False):
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                name, table, columns, unique=unique,
                postgresql_concurrently=True,
            )
    else:
        op.create_index(name, table, columns, unique=unique)


def upgrade():
    for table in TENANT_TABLES:
        _add_nullable_fk(
            table, "organisation_id", "organisations",
            f"fk_{table}_organisation_id",
        )
        _create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])

    for table in ("support_access_events", "support_delegations"):
        _add_nullable_fk(table, "organisation_id", "organisations", f"fk_{table}_organisation_id")
        _add_nullable_fk(table, "target_user_id", "users", f"fk_{table}_target_user_id")
        _create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])
        _create_index(f"ix_{table}_target_user_id", table, ["target_user_id"])

    op.add_column("users", sa.Column("session_generation", sa.Integer(), nullable=True))
    op.add_column("organisation_memberships", sa.Column("authorization_generation", sa.Integer(), nullable=True))
    op.add_column("support_principals", sa.Column("authorization_generation", sa.Integer(), nullable=True))


def downgrade():
    # Downgrade exists for disposable development/test schemas only. Production
    # rollback after this expansion is forward repair.
    op.drop_column("support_principals", "authorization_generation")
    op.drop_column("organisation_memberships", "authorization_generation")
    op.drop_column("users", "session_generation")

    for table in reversed(("support_access_events", "support_delegations")):
        op.drop_index(f"ix_{table}_target_user_id", table_name=table)
        op.drop_index(f"ix_{table}_organisation_id", table_name=table)
        if op.get_bind().dialect.name == "postgresql":
            op.drop_constraint(f"fk_{table}_target_user_id", table, type_="foreignkey")
            op.drop_constraint(f"fk_{table}_organisation_id", table, type_="foreignkey")
        op.drop_column(table, "target_user_id")
        op.drop_column(table, "organisation_id")

    for table in reversed(TENANT_TABLES):
        op.drop_index(f"ix_{table}_organisation_id", table_name=table)
        if op.get_bind().dialect.name == "postgresql":
            op.drop_constraint(f"fk_{table}_organisation_id", table, type_="foreignkey")
        op.drop_column(table, "organisation_id")
