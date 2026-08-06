"""MyFitnessPal file import foundation.

Revision ID: 0006_myfitnesspal_import
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_myfitnesspal_import"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("nutrition_provider_connections", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("import_source", sa.String(40)), sa.Column("consented_at", sa.DateTime()), sa.Column("last_import_at", sa.DateTime()), sa.Column("revoked_at", sa.DateTime()), sa.UniqueConstraint("athlete_id", "provider", name="uq_nutrition_connection"))
    op.create_index("ix_nutrition_provider_connections_athlete_id", "nutrition_provider_connections", ["athlete_id"])
    op.create_table("nutrition_import_jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("source_filename", sa.String(255), nullable=False), sa.Column("source_checksum", sa.String(64), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()), sa.Column("status", sa.String(30), nullable=False), sa.Column("daily_records_imported", sa.Integer(), nullable=False), sa.Column("warnings_json", sa.Text(), nullable=False), sa.Column("errors_json", sa.Text(), nullable=False), sa.Column("preview_json", sa.Text()))
    op.create_index("ix_nutrition_import_jobs_athlete_id", "nutrition_import_jobs", ["athlete_id"]); op.create_index("ix_nutrition_import_jobs_source_checksum", "nutrition_import_jobs", ["source_checksum"])
    op.create_table("daily_nutrition", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False), sa.Column("date", sa.Date(), nullable=False), sa.Column("calories", sa.Float()), sa.Column("protein_g", sa.Float()), sa.Column("carbohydrate_g", sa.Float()), sa.Column("fat_g", sa.Float()), sa.Column("fibre_g", sa.Float()), sa.Column("bodyweight_kg", sa.Float()), sa.Column("provider", sa.String(40), nullable=False), sa.Column("source_job_id", sa.Integer(), sa.ForeignKey("nutrition_import_jobs.id", ondelete="SET NULL")), sa.Column("imported_at", sa.DateTime(), nullable=False), sa.Column("is_partial", sa.Boolean(), nullable=False), sa.Column("notes", sa.Text()), sa.UniqueConstraint("athlete_id", "date", "provider", name="uq_daily_nutrition_source"))
    op.create_index("ix_daily_nutrition_athlete_id", "daily_nutrition", ["athlete_id"]); op.create_index("ix_daily_nutrition_date", "daily_nutrition", ["date"])
    for name, type_ in (("carbohydrate_average_g", sa.Integer()), ("fat_average_g", sa.Integer()), ("fibre_average_g", sa.Float()), ("nutrition_data_source", sa.String(40)), ("nutrition_period_start", sa.Date()), ("nutrition_period_end", sa.Date())): op.add_column("weekly_checkins", sa.Column(name, type_))


def downgrade():
    for name in ("nutrition_period_end", "nutrition_period_start", "nutrition_data_source", "fibre_average_g", "fat_average_g", "carbohydrate_average_g"): op.drop_column("weekly_checkins", name)
    op.drop_table("daily_nutrition"); op.drop_table("nutrition_import_jobs"); op.drop_table("nutrition_provider_connections")
