from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


class NutritionProviderConnection(db.Model):  # type: ignore[name-defined]
    __tablename__ = "nutrition_provider_connections"
    __table_args__ = (db.UniqueConstraint("athlete_id", "provider", name="uq_nutrition_connection"),)

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(40), nullable=False, default="myfitnesspal")
    status = db.Column(db.String(30), nullable=False, default="disconnected")
    import_source = db.Column(db.String(40))
    consented_at = db.Column(db.DateTime)
    last_import_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    athlete = db.relationship("Athlete", backref=db.backref("nutrition_connections", cascade="all, delete-orphan"))


class NutritionImportJob(db.Model):  # type: ignore[name-defined]
    __tablename__ = "nutrition_import_jobs"
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(40), nullable=False)
    source_filename = db.Column(db.String(255), nullable=False)
    source_checksum = db.Column(db.String(64), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), nullable=False, default="preview")
    daily_records_imported = db.Column(db.Integer, nullable=False, default=0)
    warnings_json = db.Column(db.Text, nullable=False, default="[]")
    errors_json = db.Column(db.Text, nullable=False, default="[]")
    preview_json = db.Column(db.Text)
    athlete = db.relationship("Athlete", backref=db.backref("nutrition_import_jobs", cascade="all, delete-orphan"))


class DailyNutrition(db.Model):  # type: ignore[name-defined]
    __tablename__ = "daily_nutrition"
    __table_args__ = (db.UniqueConstraint("athlete_id", "date", "provider", name="uq_daily_nutrition_source"),)
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    calories = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    carbohydrate_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    fibre_g = db.Column(db.Float)
    bodyweight_kg = db.Column(db.Float)
    provider = db.Column(db.String(40), nullable=False)
    source_job_id = db.Column(db.Integer, db.ForeignKey("nutrition_import_jobs.id", ondelete="SET NULL"))
    imported_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_partial = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)  # deliberately never changed by imports
    athlete = db.relationship("Athlete", backref=db.backref("daily_nutrition", cascade="all, delete-orphan"))
