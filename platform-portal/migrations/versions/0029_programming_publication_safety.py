"""Stage material programming changes before publication.

Revision ID: 0029_programming_publication_safety
Revises: 0028_spreadsheet_import_history
"""
import sqlalchemy as sa
from alembic import op

revision = "0029_programming_publication_safety"
down_revision = "0028_spreadsheet_import_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_blocks") as batch_op:
        batch_op.add_column(sa.Column("replaces_block_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_training_blocks_replaces_block_id",
            "training_blocks",
            ["replaces_block_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_training_blocks_replaces_block_id", ["replaces_block_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("training_blocks") as batch_op:
        batch_op.drop_index("ix_training_blocks_replaces_block_id")
        batch_op.drop_constraint(
            "fk_training_blocks_replaces_block_id", type_="foreignkey"
        )
        batch_op.drop_column("replaces_block_id")
