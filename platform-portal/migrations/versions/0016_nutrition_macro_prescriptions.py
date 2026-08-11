"""Add immutable, non-overlapping nutrition macro prescriptions.

Revision ID: 0016_nutrition_macros
Revises: 0015_client_services
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_nutrition_macros"
down_revision = "0015_client_services"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "nutrition_macro_prescriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("athlete_id", sa.Integer, sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_until", sa.Date),
        sa.Column("calories", sa.Integer, nullable=False),
        sa.Column("protein_g", sa.Integer, nullable=False),
        sa.Column("carbohydrate_g", sa.Integer, nullable=False),
        sa.Column("fat_g", sa.Integer, nullable=False),
        sa.Column("fibre_g", sa.Integer),
        sa.Column("training_targets", sa.JSON), sa.Column("rest_targets", sa.JSON),
        sa.Column("meal_count", sa.Integer), sa.Column("coach_notes", sa.Text),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_nutrition_macro_period"),
        sa.CheckConstraint("calories BETWEEN 500 AND 10000", name="ck_nutrition_macro_calories"),
        sa.CheckConstraint("protein_g BETWEEN 0 AND 500", name="ck_nutrition_macro_protein"),
        sa.CheckConstraint("carbohydrate_g BETWEEN 0 AND 1000", name="ck_nutrition_macro_carbohydrate"),
        sa.CheckConstraint("fat_g BETWEEN 0 AND 400", name="ck_nutrition_macro_fat"),
        sa.CheckConstraint("fibre_g IS NULL OR fibre_g BETWEEN 0 AND 150", name="ck_nutrition_macro_fibre"),
        sa.CheckConstraint("meal_count IS NULL OR meal_count BETWEEN 1 AND 12", name="ck_nutrition_macro_meals"),
    )
    op.create_index("ix_nutrition_macro_prescriptions_athlete_id", "nutrition_macro_prescriptions", ["athlete_id"])
    op.create_index("ix_nutrition_macro_prescriptions_effective_from", "nutrition_macro_prescriptions", ["effective_from"])

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute("ALTER TABLE nutrition_macro_prescriptions ADD CONSTRAINT ex_nutrition_macro_no_overlap EXCLUDE USING gist (athlete_id WITH =, daterange(effective_from, COALESCE(effective_until, 'infinity'::date), '[]') WITH &&)")
        op.execute("""CREATE FUNCTION nutrition_macro_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'nutrition macro prescriptions are append-only'; END $$""")
        op.execute("CREATE TRIGGER nutrition_macro_immutable BEFORE UPDATE OR DELETE ON nutrition_macro_prescriptions FOR EACH ROW EXECUTE FUNCTION nutrition_macro_immutable()")
    elif dialect == "sqlite":
        op.execute("""CREATE TRIGGER nutrition_macro_no_overlap BEFORE INSERT ON nutrition_macro_prescriptions WHEN EXISTS (SELECT 1 FROM nutrition_macro_prescriptions p WHERE p.athlete_id = NEW.athlete_id AND COALESCE(p.effective_until, '9999-12-31') >= NEW.effective_from AND COALESCE(NEW.effective_until, '9999-12-31') >= p.effective_from) BEGIN SELECT RAISE(ABORT, 'nutrition prescription period overlap'); END""")
        op.execute("""CREATE TRIGGER nutrition_macro_no_update BEFORE UPDATE ON nutrition_macro_prescriptions BEGIN SELECT RAISE(ABORT, 'nutrition macro prescriptions are append-only'); END""")
        op.execute("""CREATE TRIGGER nutrition_macro_no_delete BEFORE DELETE ON nutrition_macro_prescriptions BEGIN SELECT RAISE(ABORT, 'nutrition macro prescriptions are append-only'); END""")


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS nutrition_macro_immutable ON nutrition_macro_prescriptions")
        op.execute("DROP FUNCTION IF EXISTS nutrition_macro_immutable")
    op.drop_table("nutrition_macro_prescriptions")
