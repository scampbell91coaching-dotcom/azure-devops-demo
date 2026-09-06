"""Explicit programme timing and lifecycle states.

Revision ID: 0030_programme_timing_lifecycle
Revises: 0029_programming_publication_safety
"""
import sqlalchemy as sa
from alembic import op

revision = "0030_programme_timing_lifecycle"
down_revision = "0029_programming_publication_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_blocks") as batch_op:
        batch_op.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"))


def downgrade() -> None:
    with op.batch_alter_table("training_blocks") as batch_op:
        batch_op.drop_column("timezone")
        batch_op.drop_column("start_date")
