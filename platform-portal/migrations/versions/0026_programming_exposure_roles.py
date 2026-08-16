"""Add explicit coaching intent to powerlifting lift slots.

Revision ID: 0026_programming_exposure_roles
Revises: 0025_warmup_lift_slot_target
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_programming_exposure_roles"
down_revision = "0025_warmup_lift_slot_target"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("programming_lift_slots") as batch:
        batch.add_column(sa.Column("exposure_role", sa.String(32), nullable=True))
        batch.create_check_constraint(
            "ck_programming_lift_slots_exposure_role",
            "exposure_role IS NULL OR exposure_role IN ('competition', "
            "'primary_volume', 'secondary_strength', 'technique', 'low_fatigue', "
            "'overload')",
        )
        batch.create_index("ix_programming_lift_slots_exposure_role", ["exposure_role"])


def downgrade():
    with op.batch_alter_table("programming_lift_slots") as batch:
        batch.drop_index("ix_programming_lift_slots_exposure_role")
        batch.drop_constraint("ck_programming_lift_slots_exposure_role", type_="check")
        batch.drop_column("exposure_role")
