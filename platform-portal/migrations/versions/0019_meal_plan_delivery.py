"""Persist meal-plan drafts and immutable published assignment snapshots.

Revision ID: 0019_meal_plan_delivery
Revises: 0018_external_coaching_reviews
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_meal_plan_delivery"
down_revision = "0018_external_coaching_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meal_plan_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_index("ix_meal_plan_templates_coach_id", "meal_plan_templates", ["coach_id"])
    op.create_table("meal_plan_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.String(36), nullable=False), sa.Column("template_revision", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False), sa.Column("effective_until", sa.Date()),
        sa.Column("published_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_meal_plan_assignment_period"))
    op.create_index("ix_meal_plan_assignments_athlete_id", "meal_plan_assignments", ["athlete_id"])
    op.create_index("ix_meal_plan_assignments_template_id", "meal_plan_assignments", ["template_id"])
    op.create_index("ix_meal_plan_assignments_effective_from", "meal_plan_assignments", ["effective_from"])
    op.create_index("ix_meal_plan_assignments_athlete_period", "meal_plan_assignments", ["athlete_id", "effective_from", "effective_until"])


def downgrade():
    op.drop_table("meal_plan_assignments")
    op.drop_table("meal_plan_templates")
