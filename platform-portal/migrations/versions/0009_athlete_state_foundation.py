"""Add the auditable athlete-state foundation.

Revision ID: 0009_athlete_state
Revises: 0008_athlete_training_logs
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_athlete_state"
down_revision = "0008_athlete_training_logs"
branch_labels = None
depends_on = None


def _athlete_fk():
    return sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE")


def upgrade():
    op.create_table(
        "athlete_state_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(160)),
        sa.Column("effective_on", sa.Date()),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_by", sa.String(160)),
        sa.Column("supersedes_id", sa.Integer()),
        sa.CheckConstraint("source_type IN ('athlete', 'coach', 'import', 'legacy')", name="ck_athlete_state_facts_source"),
        _athlete_fk(),
        sa.ForeignKeyConstraint(["supersedes_id"], ["athlete_state_facts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("supersedes_id"),
    )
    op.create_index("ix_athlete_state_facts_athlete_id", "athlete_state_facts", ["athlete_id"])
    op.create_index("ix_athlete_state_facts_fact_type", "athlete_state_facts", ["fact_type"])

    op.create_table(
        "coach_technical_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("lift", sa.String(20), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("source_ref", sa.String(160)),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_by", sa.String(160), nullable=False),
        sa.Column("superseded_by_id", sa.Integer()),
        _athlete_fk(),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["coach_technical_observations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("superseded_by_id"),
    )
    op.create_index("ix_coach_technical_observations_athlete_id", "coach_technical_observations", ["athlete_id"])
    op.create_index("ix_coach_technical_observations_lift", "coach_technical_observations", ["lift"])

    op.create_table(
        "athlete_constraint_flags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("flag_kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("details", sa.Text()),
        sa.Column("reported_by", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(160)),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("resolved_on", sa.Date()),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("flag_kind IN ('irritation', 'constraint')", name="ck_athlete_constraint_flags_kind"),
        sa.CheckConstraint("reported_by IN ('athlete', 'coach')", name="ck_athlete_constraint_flags_reporter"),
        _athlete_fk(),
    )
    op.create_index("ix_athlete_constraint_flags_athlete_id", "athlete_constraint_flags", ["athlete_id"])

    op.create_table(
        "athlete_state_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("signal_type", sa.String(80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("window_start", sa.Date()), sa.Column("window_end", sa.Date()),
        sa.Column("calculation_version", sa.String(40), nullable=False),
        sa.Column("source_refs_json", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        _athlete_fk(),
    )
    for column in ("athlete_id", "snapshot_id", "signal_type"):
        op.create_index(f"ix_athlete_state_signals_{column}", "athlete_state_signals", [column])

    op.create_table(
        "athlete_state_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_type", sa.String(80), nullable=False), sa.Column("recommendation_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False), sa.Column("signal_ids_json", sa.JSON(), nullable=False),
        sa.Column("generator_version", sa.String(40), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False), sa.Column("decided_at", sa.DateTime()), sa.Column("decided_by", sa.String(160)),
        sa.CheckConstraint("status IN ('proposed', 'accepted', 'dismissed', 'superseded')", name="ck_athlete_state_recommendations_status"), _athlete_fk(),
    )
    op.create_index("ix_athlete_state_recommendations_athlete_id", "athlete_state_recommendations", ["athlete_id"])
    op.create_index("ix_athlete_state_recommendations_recommendation_type", "athlete_state_recommendations", ["recommendation_type"])

    op.create_table(
        "athlete_state_overrides",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False), sa.Column("target_ref", sa.String(160), nullable=False),
        sa.Column("override_json", sa.JSON(), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.String(160), nullable=False), sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()), sa.Column("revoked_at", sa.DateTime()), _athlete_fk(),
    )
    op.create_index("ix_athlete_state_overrides_athlete_id", "athlete_state_overrides", ["athlete_id"])


def downgrade():
    for table in ("athlete_state_overrides", "athlete_state_recommendations", "athlete_state_signals", "athlete_constraint_flags", "coach_technical_observations", "athlete_state_facts"):
        op.drop_table(table)
