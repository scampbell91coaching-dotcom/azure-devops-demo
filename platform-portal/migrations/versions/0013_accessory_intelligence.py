"""Add opt-in accessory selection metadata to the exercise library.

Revision ID: 0013_accessory_intelligence
Revises: 0012_athlete_accounts
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_accessory_intelligence"
down_revision = "0012_athlete_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column("auto_select", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("lift_relevance", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("training_phases", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("compatibility_tags", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("coach_priority", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index("ix_exercises_auto_select", ["auto_select"])


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_index("ix_exercises_auto_select")
        for column in (
            "coach_priority",
            "compatibility_tags",
            "training_phases",
            "lift_relevance",
            "auto_select",
        ):
            batch_op.drop_column(column)
