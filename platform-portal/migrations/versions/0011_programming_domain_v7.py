"""Add durable lift slots and structured prescription metadata.

Revision ID: 0010_programming_v7
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_programming_v7"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "programming_lift_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("lift_family", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "lift_family IN ('squat', 'bench', 'deadlift')",
            name="ck_programming_lift_slots_family",
        ),
        sa.CheckConstraint("position > 0", name="ck_programming_lift_slots_position"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["training_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "position", name="uq_programming_lift_slots_position"
        ),
    )
    op.create_index(
        "ix_programming_lift_slots_session_id",
        "programming_lift_slots",
        ["session_id"],
    )
    op.create_index(
        "ix_programming_lift_slots_lift_family",
        "programming_lift_slots",
        ["lift_family"],
    )

    with op.batch_alter_table("exercise_prescriptions") as batch_op:
        batch_op.add_column(sa.Column("exercise_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lift_slot_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("slot_role", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("rpe_min", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("rpe_max", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("provenance", sa.String(length=30), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_exercise_prescriptions_exercise_id",
            "exercises",
            ["exercise_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_exercise_prescriptions_lift_slot_id",
            "programming_lift_slots",
            ["lift_slot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_exercise_prescriptions_slot_role",
            "slot_role IS NULL OR slot_role IN ('top_set', 'back_off')",
        )
        batch_op.create_check_constraint(
            "ck_exercise_prescriptions_provenance",
            "provenance IS NULL OR provenance IN "
            "('generated', 'coach_selected', 'coach_authored')",
        )
        batch_op.create_check_constraint(
            "ck_exercise_prescriptions_rpe_min",
            "rpe_min IS NULL OR (rpe_min >= 1 AND rpe_min <= 10)",
        )
        batch_op.create_check_constraint(
            "ck_exercise_prescriptions_rpe_max",
            "rpe_max IS NULL OR (rpe_max >= 1 AND rpe_max <= 10)",
        )
        batch_op.create_check_constraint(
            "ck_exercise_prescriptions_rpe_range",
            "(rpe_min IS NULL AND rpe_max IS NULL) OR "
            "(rpe_min IS NOT NULL AND rpe_max IS NOT NULL AND rpe_min <= rpe_max)",
        )
        batch_op.create_index(
            "ix_exercise_prescriptions_exercise_id", ["exercise_id"]
        )
        batch_op.create_index(
            "ix_exercise_prescriptions_lift_slot_id", ["lift_slot_id"]
        )

    # Exact-name matches are unambiguous because exercises.name is unique. Slots,
    # roles, RPE bounds, and provenance cannot be inferred safely from legacy rows.
    op.execute(
        sa.text(
            "UPDATE exercise_prescriptions SET exercise_id = "
            "(SELECT exercises.id FROM exercises "
            "WHERE exercises.name = exercise_prescriptions.exercise_name) "
            "WHERE EXISTS (SELECT 1 FROM exercises "
            "WHERE exercises.name = exercise_prescriptions.exercise_name)"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("exercise_prescriptions") as batch_op:
        for constraint in (
            "ck_exercise_prescriptions_rpe_range",
            "ck_exercise_prescriptions_rpe_max",
            "ck_exercise_prescriptions_rpe_min",
            "ck_exercise_prescriptions_provenance",
            "ck_exercise_prescriptions_slot_role",
        ):
            batch_op.drop_constraint(constraint, type_="check")
        batch_op.drop_index("ix_exercise_prescriptions_lift_slot_id")
        batch_op.drop_index("ix_exercise_prescriptions_exercise_id")
        batch_op.drop_constraint(
            "fk_exercise_prescriptions_lift_slot_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_exercise_prescriptions_exercise_id", type_="foreignkey"
        )
        for name in (
            "provenance",
            "rpe_max",
            "rpe_min",
            "slot_role",
            "lift_slot_id",
            "exercise_id",
        ):
            batch_op.drop_column(name)
    op.drop_index(
        "ix_programming_lift_slots_lift_family",
        table_name="programming_lift_slots",
    )
    op.drop_index(
        "ix_programming_lift_slots_session_id",
        table_name="programming_lift_slots",
    )
    op.drop_table("programming_lift_slots")
