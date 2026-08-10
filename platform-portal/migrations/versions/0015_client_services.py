"""Add append-only client service decisions.

Revision ID: 0015_client_services
Revises: 0014_warmup_integration
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_client_services"
down_revision = "0014_warmup_integration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_service_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("value", sa.String(16), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("service IN ('training', 'nutrition', 'meet_day', 'video_review')", name="ck_client_service_changes_service"),
        sa.CheckConstraint("value IN ('yes', 'no', 'none', 'limited', 'included')", name="ck_client_service_changes_value"),
    )
    for column in ("athlete_id", "service", "effective_at"):
        op.create_index(f"ix_client_service_changes_{column}", "client_service_changes", [column])


def downgrade():
    op.drop_table("client_service_changes")
