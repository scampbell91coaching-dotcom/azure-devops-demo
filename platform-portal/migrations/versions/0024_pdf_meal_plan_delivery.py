"""Add immutable, tenant-scoped PDF meal-plan delivery.

Revision ID: 0024_pdf_meal_plan_delivery
Revises: 0023_organisation_invitation_delivery
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_pdf_meal_plan_delivery"
down_revision = "0023_organisation_invitation_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pdf_meal_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_pdf_meal_plan_status"),
        sa.UniqueConstraint("organisation_id", "athlete_id", "revision", name="uq_pdf_meal_plan_org_athlete_revision"),
    )
    for column in ("organisation_id", "athlete_id", "coach_id", "status", "effective_from"):
        op.create_index(f"ix_pdf_meal_plans_{column}", "pdf_meal_plans", [column])


def downgrade():
    op.drop_table("pdf_meal_plans")
