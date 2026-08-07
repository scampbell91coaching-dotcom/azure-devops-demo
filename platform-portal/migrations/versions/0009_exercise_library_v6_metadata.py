"""Add nullable Exercise Library V6 swap metadata.

Revision ID: 0009
Revises: 0008_athlete_training_logs
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008_athlete_training_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(sa.Column("lift_family", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("movement_pattern", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("specificity", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("technical_purposes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("equipment_options", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("constraint_tags", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("variation_of", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("swap_group", sa.String(80), nullable=True))
        batch_op.create_index("ix_exercises_lift_family", ["lift_family"])
        batch_op.create_index("ix_exercises_movement_pattern", ["movement_pattern"])
        batch_op.create_index("ix_exercises_swap_group", ["swap_group"])


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_index("ix_exercises_swap_group")
        batch_op.drop_index("ix_exercises_movement_pattern")
        batch_op.drop_index("ix_exercises_lift_family")
        for column in (
            "swap_group", "variation_of", "constraint_tags", "equipment_options",
            "technical_purposes", "specificity", "movement_pattern", "lift_family",
        ):
            batch_op.drop_column(column)
