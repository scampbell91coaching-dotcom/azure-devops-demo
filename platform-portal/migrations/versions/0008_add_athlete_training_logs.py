"""Add athlete session logs and per-set training results.

Revision ID: 0006
Revises: 0005

Migration ordering may need adjustment before integration because other local
branches are awaiting merge.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_athlete_training_logs"
down_revision = "0007_myfitnesspal_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_session_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("session_name", sa.String(length=120), nullable=False),
        sa.Column("block_name", sa.String(length=160), nullable=False),
        sa.Column("week_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed')",
            name="ck_training_session_logs_status",
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["training_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "athlete_id", "session_id", name="uq_training_session_logs_assignment"
        ),
    )
    op.create_index(
        "ix_training_session_logs_athlete_id", "training_session_logs", ["athlete_id"]
    )
    op.create_index(
        "ix_training_session_logs_session_id", "training_session_logs", ["session_id"]
    )
    op.create_index(
        "ix_training_session_logs_status", "training_session_logs", ["status"]
    )
    op.create_index(
        "ix_training_session_logs_completed_at",
        "training_session_logs",
        ["completed_at"],
    )

    op.create_table(
        "training_set_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_log_id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=True),
        sa.Column("exercise_name", sa.String(length=160), nullable=False),
        sa.Column("exercise_position", sa.Integer(), nullable=False),
        sa.Column("set_order", sa.Integer(), nullable=False),
        sa.Column("is_extra", sa.Boolean(), nullable=False),
        sa.Column("prescribed_reps", sa.String(length=40), nullable=True),
        sa.Column("prescribed_load_kg", sa.Float(), nullable=True),
        sa.Column("prescribed_rpe", sa.Float(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False),
        sa.Column("actual_load_kg", sa.Float(), nullable=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("actual_rpe", sa.Float(), nullable=True),
        sa.Column("athlete_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("set_order > 0", name="ck_training_set_results_order"),
        sa.CheckConstraint("actual_load_kg >= 0", name="ck_training_set_results_load"),
        sa.CheckConstraint("actual_reps >= 0", name="ck_training_set_results_reps"),
        sa.CheckConstraint(
            "actual_rpe >= 1 AND actual_rpe <= 10",
            name="ck_training_set_results_rpe",
        ),
        sa.CheckConstraint(
            "NOT (completed AND skipped)",
            name="ck_training_set_results_single_state",
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"], ["exercise_prescriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_log_id"], ["training_session_logs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_log_id",
            "exercise_position",
            "set_order",
            name="uq_training_set_results_order",
        ),
    )
    op.create_index(
        "ix_training_set_results_session_log_id",
        "training_set_results",
        ["session_log_id"],
    )
    op.create_index(
        "ix_training_set_results_prescription_id",
        "training_set_results",
        ["prescription_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_set_results_prescription_id", table_name="training_set_results"
    )
    op.drop_index(
        "ix_training_set_results_session_log_id", table_name="training_set_results"
    )
    op.drop_table("training_set_results")
    op.drop_index(
        "ix_training_session_logs_completed_at", table_name="training_session_logs"
    )
    op.drop_index("ix_training_session_logs_status", table_name="training_session_logs")
    op.drop_index(
        "ix_training_session_logs_session_id", table_name="training_session_logs"
    )
    op.drop_index(
        "ix_training_session_logs_athlete_id", table_name="training_session_logs"
    )
    op.drop_table("training_session_logs")
