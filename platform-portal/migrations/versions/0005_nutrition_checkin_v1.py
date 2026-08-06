"""Expand nutrition check-ins for the V1 workflow.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("nutrition_checkins", sa.Column("checkin_date", sa.Date(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("calorie_target", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("protein_target_g", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("carbohydrate_target_g", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("average_carbohydrate_g", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("fat_target_g", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("average_fat_g", sa.Integer(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("average_fibre_g", sa.Float(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("average_fluid_l", sa.Float(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("average_sleep_hours", sa.Float(), nullable=True))
    op.add_column("nutrition_checkins", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE nutrition_checkins SET checkin_date = CAST(submitted_at AS DATE) WHERE checkin_date IS NULL")
    with op.batch_alter_table("nutrition_checkins") as batch_op:
        batch_op.alter_column("checkin_date", nullable=False)
    op.create_index("ix_nutrition_checkins_checkin_date", "nutrition_checkins", ["checkin_date"])


def downgrade():
    op.drop_index("ix_nutrition_checkins_checkin_date", table_name="nutrition_checkins")
    for column in (
        "reviewed_at", "average_sleep_hours", "average_fluid_l", "average_fibre_g",
        "average_fat_g", "fat_target_g", "average_carbohydrate_g",
        "carbohydrate_target_g", "protein_target_g", "calorie_target", "checkin_date",
    ):
        op.drop_column("nutrition_checkins", column)
