"""Spreadsheet history import provenance.

Revision ID: 0028_spreadsheet_import_history
Revises: 0027_tenancy_ownership_expand
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_spreadsheet_import_history"
down_revision = "0027_tenancy_ownership_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("spreadsheet_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("imported_by_user_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("rows_skipped_duplicate", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"], ondelete="SET NULL"))
    op.create_index("ix_spreadsheet_import_batches_organisation_id", "spreadsheet_import_batches", ["organisation_id"])
    op.create_index("ix_spreadsheet_import_batches_athlete_id", "spreadsheet_import_batches", ["athlete_id"])
    op.create_index("ix_spreadsheet_import_batches_imported_at", "spreadsheet_import_batches", ["imported_at"])
    op.create_table("spreadsheet_import_provenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("training_set_result_id", sa.Integer(), nullable=False),
        sa.Column("source_sheet", sa.String(255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("semantic_fingerprint", sa.String(64), nullable=False),
        sa.Column("semantic_values", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["spreadsheet_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["training_set_result_id"], ["training_set_results.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("athlete_id", "semantic_fingerprint", name="uq_spreadsheet_import_semantic_row"),
        sa.UniqueConstraint("training_set_result_id", name="uq_spreadsheet_import_result"))
    op.create_index("ix_spreadsheet_import_provenance_organisation_id", "spreadsheet_import_provenance", ["organisation_id"])
    op.create_index("ix_spreadsheet_import_provenance_athlete_id", "spreadsheet_import_provenance", ["athlete_id"])
    op.create_index("ix_spreadsheet_import_provenance_batch_id", "spreadsheet_import_provenance", ["batch_id"])


def downgrade() -> None:
    op.drop_table("spreadsheet_import_provenance")
    op.drop_table("spreadsheet_import_batches")
