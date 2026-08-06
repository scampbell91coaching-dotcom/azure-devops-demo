"""Add Meet Day competition metadata.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("meets") as batch:
        batch.add_column(sa.Column("federation", sa.String(80)))
        batch.add_column(sa.Column("bodyweight_kg", sa.Numeric(6, 2)))
        batch.add_column(sa.Column("weight_class", sa.String(40)))


def downgrade() -> None:
    with op.batch_alter_table("meets") as batch:
        batch.drop_column("weight_class")
        batch.drop_column("bodyweight_kg")
        batch.drop_column("federation")
