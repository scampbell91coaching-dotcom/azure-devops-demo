"""Add immutable programme revision history."""
import sqlalchemy as sa
from alembic import op
revision = "0017_programme_revision_history"
down_revision = "0016_nutrition_macros"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("programme_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("block_id", sa.Integer(), sa.ForeignKey("training_blocks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(80), nullable=False),
        sa.Column("summary", sa.String(240), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authored_snapshot", sa.JSON(), nullable=False),
        sa.Column("authored_at", sa.DateTime(), nullable=False),
        sa.Column("authored_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("authored_by", sa.String(255), nullable=False),
        sa.CheckConstraint("revision_number > 0", name="ck_programme_revisions_number"),
        sa.UniqueConstraint("block_id", "revision_number", name="uq_programme_revisions_number"))
    op.create_index("ix_programme_revisions_block_id", "programme_revisions", ["block_id"])
    op.create_index("ix_programme_revisions_athlete_id", "programme_revisions", ["athlete_id"])
    op.create_index("ix_programme_revisions_authored_at", "programme_revisions", ["authored_at"])
def downgrade():
    op.drop_table("programme_revisions")
