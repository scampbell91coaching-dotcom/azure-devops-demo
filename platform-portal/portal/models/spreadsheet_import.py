from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class SpreadsheetImportBatch(db.Model):  # type: ignore[name-defined]
    __tablename__ = "spreadsheet_import_batches"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    imported_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_filename = db.Column(db.String(255), nullable=False)
    source_checksum = db.Column(db.String(64), nullable=False)
    imported_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)
    rows_imported = db.Column(db.Integer, nullable=False, default=0)
    rows_skipped_duplicate = db.Column(db.Integer, nullable=False, default=0)
    rows_rejected = db.Column(db.Integer, nullable=False, default=0)


class SpreadsheetImportProvenance(db.Model):  # type: ignore[name-defined]
    __tablename__ = "spreadsheet_import_provenance"
    __table_args__ = (
        db.UniqueConstraint("athlete_id", "semantic_fingerprint", name="uq_spreadsheet_import_semantic_row"),
        db.UniqueConstraint("training_set_result_id", name="uq_spreadsheet_import_result"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("spreadsheet_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    training_set_result_id = db.Column(db.Integer, db.ForeignKey("training_set_results.id", ondelete="CASCADE"), nullable=False)
    source_sheet = db.Column(db.String(255), nullable=False)
    source_row = db.Column(db.Integer, nullable=False)
    semantic_fingerprint = db.Column(db.String(64), nullable=False)
    semantic_values = db.Column(db.JSON, nullable=False)
    imported_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    batch = db.relationship("SpreadsheetImportBatch")
    result = db.relationship("TrainingSetResult", backref=db.backref("import_provenance", uselist=False))
