"""Add the external WhatsApp coaching review prototype.

Revision ID: whatsapp_external_review
Revises: 0015_client_services
"""

import sqlalchemy as sa
from alembic import op

revision = "whatsapp_external_review"
down_revision = "0015_client_services"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_coaching_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("session_log_id", sa.Integer(), sa.ForeignKey("training_session_logs.id", ondelete="SET NULL")),
        sa.Column("set_result_id", sa.Integer(), sa.ForeignKey("training_set_results.id", ondelete="SET NULL")),
        sa.Column("observation_id", sa.Integer(), sa.ForeignKey("coach_technical_observations.id", ondelete="SET NULL")),
        sa.Column("coach_summary", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("follow_up_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("external_url", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("channel = 'whatsapp'", name="ck_external_reviews_channel"),
    )
    for column in ("athlete_id", "reviewed_at", "session_log_id", "set_result_id", "observation_id"):
        op.create_index(f"ix_external_coaching_reviews_{column}", "external_coaching_reviews", [column])


def downgrade():
    op.drop_table("external_coaching_reviews")
