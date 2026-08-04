"""Add coach-controlled meet-day workflow.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("meet_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'complete')", name="ck_meets_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meets_meet_date", "meets", ["meet_date"])
    op.create_index("ix_meets_status", "meets", ["status"])
    op.create_table(
        "meet_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meet_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("flight", sa.Integer(), nullable=False),
        sa.Column("platform_order", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint("flight >= 1", name="ck_meet_entries_flight"),
        sa.CheckConstraint("platform_order >= 1", name="ck_meet_entries_order"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meet_id"], ["meets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meet_id", "athlete_id", name="uq_meet_entries_athlete"),
    )
    op.create_index("ix_meet_entries_athlete_id", "meet_entries", ["athlete_id"])
    op.create_index("ix_meet_entries_meet_id", "meet_entries", ["meet_id"])
    op.create_table(
        "meet_lifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("lift", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2)),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "lift IN ('squat', 'bench', 'deadlift')", name="ck_meet_lifts_lift"
        ),
        sa.CheckConstraint("kind IN ('warmup', 'attempt')", name="ck_meet_lifts_kind"),
        sa.CheckConstraint(
            "outcome IN ('pending', 'good', 'miss', 'skipped')",
            name="ck_meet_lifts_outcome",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_meet_lifts_sequence"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0", name="ck_meet_lifts_weight"
        ),
        sa.ForeignKeyConstraint(["entry_id"], ["meet_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "lift", "kind", "sequence", name="uq_meet_lifts_slot"
        ),
    )
    op.create_index("ix_meet_lifts_entry_id", "meet_lifts", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_meet_lifts_entry_id", table_name="meet_lifts")
    op.drop_table("meet_lifts")
    op.drop_index("ix_meet_entries_meet_id", table_name="meet_entries")
    op.drop_index("ix_meet_entries_athlete_id", table_name="meet_entries")
    op.drop_table("meet_entries")
    op.drop_index("ix_meets_status", table_name="meets")
    op.drop_index("ix_meets_meet_date", table_name="meets")
    op.drop_table("meets")
