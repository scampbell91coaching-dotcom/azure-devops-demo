"""Target assigned warm-ups to an explicit programming lift slot.

Revision ID: 0025_warmup_lift_slot_target
Revises: 0024_pdf_meal_plan_delivery
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_warmup_lift_slot_target"
down_revision = "0024_pdf_meal_plan_delivery"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("warmup_assignments") as batch:
        batch.add_column(sa.Column("lift_slot_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_warmup_assignments_lift_slot_id", "programming_lift_slots",
            ["lift_slot_id"], ["id"], ondelete="CASCADE",
        )
    op.create_index(
        "ix_warmup_assignments_lift_slot_id", "warmup_assignments", ["lift_slot_id"]
    )


def downgrade():
    op.drop_index("ix_warmup_assignments_lift_slot_id", table_name="warmup_assignments")
    with op.batch_alter_table("warmup_assignments") as batch:
        batch.drop_constraint("fk_warmup_assignments_lift_slot_id", type_="foreignkey")
        batch.drop_column("lift_slot_id")
