from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from .extensions import db
from .models.athlete import Athlete
from .models.nutrition_import import DailyNutrition, NutritionImportJob, NutritionProviderConnection
from .services.nutrition_import.myfitnesspal import ImportFormatError, MyFitnessPalFileProvider
from .services.nutrition_entitlements import nutrition_coaching_enabled
from .tenancy import require_athlete_access

nutrition_imports_bp = Blueprint("nutrition_imports", __name__)


def _athlete_access(athlete_id: int) -> Athlete:
    return require_athlete_access(athlete_id)


def _active_nutrition_access(athlete_id: int) -> Athlete:
    athlete = _athlete_access(athlete_id)
    if not nutrition_coaching_enabled(athlete):
        abort(403)
    return athlete


def _summary(athlete_id: int, start: date, end: date) -> dict[str, object]:
    rows = DailyNutrition.query.filter(DailyNutrition.athlete_id == athlete_id, DailyNutrition.date >= start, DailyNutrition.date <= end).order_by(DailyNutrition.date).all()
    fields = ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g", "bodyweight_kg")
    averages = {}
    for field in fields:
        values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
        averages[field] = round(sum(values) / len(values), 1) if values else None
    return {"rows": rows, "averages": averages, "expected_days": (end - start).days + 1, "complete_days": sum(not row.is_partial for row in rows)}


@nutrition_imports_bp.get("/athletes/<int:athlete_id>/nutrition-import")
def index(athlete_id: int):
    athlete = _active_nutrition_access(athlete_id)
    connection = NutritionProviderConnection.query.filter_by(athlete_id=athlete.id, provider="myfitnesspal").first()
    today = datetime.now(UTC).date()
    return render_template("nutrition_import/index.html", athlete=athlete, athlete_navigation_id=athlete.id, connection=connection, summary=_summary(athlete.id, today - timedelta(days=6), today))


@nutrition_imports_bp.post("/athletes/<int:athlete_id>/nutrition-import/preview")
def preview(athlete_id: int):
    athlete = _active_nutrition_access(athlete_id)
    upload = request.files.get("export")
    if request.form.get("consent") != "1":
        return render_template("nutrition_import/index.html", athlete=athlete, athlete_navigation_id=athlete.id, connection=None, summary=_summary(athlete.id, date.today() - timedelta(days=6), date.today()), error="Consent is required before importing."), 400
    if upload is None or not upload.filename:
        abort(400, description="Choose an export file.")
    payload = upload.stream.read(int(current_app.config["NUTRITION_UPLOAD_MAX_BYTES"]) + 1)
    if len(payload) > int(current_app.config["NUTRITION_UPLOAD_MAX_BYTES"]):
        abort(413)
    try:
        result = MyFitnessPalFileProvider().preview(payload, upload.filename)
    except ImportFormatError as exc:
        return render_template("nutrition_import/index.html", athlete=athlete, athlete_navigation_id=athlete.id, connection=None, summary=_summary(athlete.id, date.today() - timedelta(days=6), date.today()), error=str(exc)), 400
    job = NutritionImportJob(athlete=athlete, provider="myfitnesspal", source_filename=upload.filename[:255], source_checksum=result.checksum, warnings_json=json.dumps(result.warnings), preview_json=json.dumps(result.rows))
    db.session.add(job)
    db.session.commit()  # raw upload is intentionally not retained
    return render_template("nutrition_import/preview.html", athlete=athlete, athlete_navigation_id=athlete.id, job=job, rows=result.rows, warnings=result.warnings)


@nutrition_imports_bp.post("/athletes/<int:athlete_id>/nutrition-import/<int:job_id>/commit")
def commit(athlete_id: int, job_id: int):
    athlete = _active_nutrition_access(athlete_id)
    job = NutritionImportJob.query.filter_by(id=job_id, athlete_id=athlete.id, status="preview").first_or_404()
    rows = json.loads(job.preview_json or "[]")
    for item in rows:
        day = date.fromisoformat(item["date"])
        record = DailyNutrition.query.filter_by(athlete_id=athlete.id, date=day, provider="myfitnesspal").first()
        if record is None:
            record = DailyNutrition(athlete=athlete, date=day, provider="myfitnesspal")
            db.session.add(record)
        for field in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g", "bodyweight_kg", "is_partial"):
            setattr(record, field, item.get(field))
        record.source_job_id = job.id
        record.imported_at = datetime.now(UTC)
    now = datetime.now(UTC)
    job.status, job.completed_at, job.daily_records_imported, job.preview_json = "completed", now, len(rows), None
    connection = NutritionProviderConnection.query.filter_by(athlete_id=athlete.id, provider="myfitnesspal").first()
    if connection is None:
        connection = NutritionProviderConnection(athlete=athlete, provider="myfitnesspal")
        db.session.add(connection)
    connection.status, connection.import_source, connection.consented_at, connection.last_import_at, connection.revoked_at = "connected", "file_upload", connection.consented_at or job.started_at, now, None
    db.session.commit()
    return redirect(url_for("nutrition_imports.index", athlete_id=athlete.id))


@nutrition_imports_bp.post("/athletes/<int:athlete_id>/nutrition-import/disconnect")
def disconnect(athlete_id: int):
    athlete = _active_nutrition_access(athlete_id)
    DailyNutrition.query.filter_by(athlete_id=athlete.id, provider="myfitnesspal").delete()
    connection = NutritionProviderConnection.query.filter_by(athlete_id=athlete.id, provider="myfitnesspal").first()
    if connection:
        connection.status, connection.revoked_at = "revoked", datetime.now(UTC)
    for job in NutritionImportJob.query.filter_by(athlete_id=athlete.id, provider="myfitnesspal"):
        job.preview_json = None
    db.session.commit()
    return redirect(url_for("nutrition_imports.index", athlete_id=athlete.id))
