"""Add enriched exercise knowledge columns.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column(
                "accessory_suitable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("catalogue_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cautions", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("common_mistakes", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("competition_relevance", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column("difficulty", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(sa.Column("execution", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("goal", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("prescription_styles", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("progressions", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("regressions", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("rep_ranges", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(sa.Column("setup", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "warmup_suitable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_column("warmup_suitable")
        batch_op.drop_column("setup")
        batch_op.drop_column("rep_ranges")
        batch_op.drop_column("regressions")
        batch_op.drop_column("progressions")
        batch_op.drop_column("prescription_styles")
        batch_op.drop_column("goal")
        batch_op.drop_column("execution")
        batch_op.drop_column("difficulty")
        batch_op.drop_column("competition_relevance")
        batch_op.drop_column("common_mistakes")
        batch_op.drop_column("cautions")
        batch_op.drop_column("catalogue_version")
        batch_op.drop_column("accessory_suitable")
