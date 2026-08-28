from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from flask import Blueprint, abort, current_app, g, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from .auth import roles_required
from .extensions import db
from .models.spreadsheet_import import SpreadsheetImportBatch, SpreadsheetImportProvenance
from .models.programming import TrainingSessionLog, TrainingSetResult
from .models.user import UserRole
from .observability import record_spreadsheet_import
from .services.spreadsheet_import import FIELDS, ImportFormatError, detect, fingerprint, interpret, read_workbook
from .tenancy import current_tenancy_context, require_athlete_access

spreadsheet_imports_bp = Blueprint("spreadsheet_imports", __name__)
TOKEN_SALT = "spreadsheet-import-preview-v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=TOKEN_SALT)


def _load_token(value: str) -> dict:
    try:
        data = _serializer().loads(value, max_age=int(current_app.config["SPREADSHEET_PREVIEW_MAX_AGE_SECONDS"]))
    except (BadSignature, SignatureExpired):
        abort(400, description="This import preview has expired or was changed. Upload the file again.")
    if not isinstance(data, dict): abort(400)
    return data


def _athlete(athlete_id: int):
    return require_athlete_access(athlete_id)


@spreadsheet_imports_bp.get("/athletes/<int:athlete_id>/spreadsheet-import")
@roles_required(UserRole.COACH)
def index(athlete_id: int):
    return render_template("spreadsheet_import/upload.html", athlete=_athlete(athlete_id), athlete_navigation_id=athlete_id)


@spreadsheet_imports_bp.post("/athletes/<int:athlete_id>/spreadsheet-import/map")
@roles_required(UserRole.COACH)
def mapping(athlete_id: int):
    athlete = _athlete(athlete_id)
    preview_token = request.form.get("preview_token", "")
    if preview_token:
        data = _load_token(preview_token)
        if data.get("athlete_id") != athlete.id: abort(403)
        inferred = detect(data["sheet"])
        selected_by_column = {column: field for field, column in data.get("mapping", {}).items()}
        for column in inferred["columns"]:
            column["field"] = selected_by_column.get(column["index"])
        return render_template("spreadsheet_import/map.html", athlete=athlete, token=preview_token,
            sheet=data["sheet"], sheet_names=data["sheet_names"], inferred=inferred, fields=FIELDS,
            formula_cells=data.get("formula_cells", 0))
    upload = request.files.get("spreadsheet")
    if upload is None or not upload.filename: abort(400, description="Choose a CSV or XLSX file.")
    limit = int(current_app.config["SPREADSHEET_UPLOAD_MAX_BYTES"])
    payload = upload.stream.read(limit + 1)
    if len(payload) > limit: abort(413)
    record_spreadsheet_import("started")
    try:
        workbook = read_workbook(payload, upload.filename)
        candidates = [(len(detect(sheet)["mapping"]), i) for i, sheet in enumerate(workbook.sheets)]
        sheet_index = max(candidates)[1]
        sheet, inferred = workbook.sheets[sheet_index], detect(workbook.sheets[sheet_index])
    except ImportFormatError as exc:
        record_spreadsheet_import("failed")
        return render_template("spreadsheet_import/upload.html", athlete=athlete, athlete_navigation_id=athlete.id, error=str(exc)), 400
    safe_name = secure_filename(workbook.filename)[:255] or "spreadsheet"
    token = _serializer().dumps({"athlete_id": athlete.id, "filename": safe_name, "checksum": workbook.checksum,
        "sheet": sheet, "sheet_index": sheet_index, "sheet_names": [s["name"] for s in workbook.sheets], "header_row": inferred["header_row"], "formula_cells": workbook.formula_cells})
    return render_template("spreadsheet_import/map.html", athlete=athlete, token=token, sheet=sheet, sheet_names=[s["name"] for s in workbook.sheets], inferred=inferred, fields=FIELDS, formula_cells=workbook.formula_cells)


@spreadsheet_imports_bp.post("/athletes/<int:athlete_id>/spreadsheet-import/review")
@roles_required(UserRole.COACH)
def review(athlete_id: int):
    athlete = _athlete(athlete_id)
    data = _load_token(request.form.get("preview_token", ""))
    if data.get("athlete_id") != athlete.id: abort(403)
    mapping = {}
    for key, value in request.form.items():
        if key.startswith("column_") and value in FIELDS:
            if value in mapping: abort(400, description=f"Map {value} only once.")
            mapping[value] = int(key.removeprefix("column_"))
    try: rows = interpret(data["sheet"], int(data["header_row"]), mapping)
    except ImportFormatError as exc: abort(400, description=str(exc))
    fingerprints = [fingerprint(row, set_no) for row in rows if not row["errors"] for set_no in range(1, row["sets_value"] + 1)]
    existing = set()
    if fingerprints:
        existing = {p.semantic_fingerprint for p in SpreadsheetImportProvenance.query.filter(SpreadsheetImportProvenance.athlete_id == athlete.id, SpreadsheetImportProvenance.semantic_fingerprint.in_(fingerprints)).all()}
    duplicate_count = sum(fp in existing for fp in fingerprints)
    invalid_count = sum(bool(row["errors"]) for row in rows)
    review_token = _serializer().dumps({**data, "mapping": mapping})
    record_spreadsheet_import("previewed")
    return render_template("spreadsheet_import/review.html", athlete=athlete, token=review_token, rows=rows, duplicate_count=duplicate_count,
        invalid_count=invalid_count, import_count=len(fingerprints)-duplicate_count, formula_cells=data.get("formula_cells", 0))


@spreadsheet_imports_bp.post("/athletes/<int:athlete_id>/spreadsheet-import/commit")
@roles_required(UserRole.COACH)
def commit(athlete_id: int):
    athlete = _athlete(athlete_id)
    data = _load_token(request.form.get("preview_token", ""))
    if data.get("athlete_id") != athlete.id: abort(403)
    if request.form.get("confirm") != "yes": abort(400, description="Explicit import confirmation is required.")
    rows = interpret(data["sheet"], int(data["header_row"]), data["mapping"])
    organisation_id = current_tenancy_context().organisation_id
    batch = SpreadsheetImportBatch(organisation_id=organisation_id, athlete_id=athlete.id,
        imported_by_user_id=getattr(g.get("current_user"), "id", None), source_filename=data["filename"], source_checksum=data["checksum"])
    imported = duplicates = rejected = 0
    logs = {}
    try:
        db.session.add(batch)
        for row in rows:
            if row["errors"]:
                rejected += 1
                continue
            group = (row["date_value"] or "", row["week"], row["session"])
            log = logs.get(group)
            for set_no in range(1, row["sets_value"] + 1):
                semantic = fingerprint(row, set_no)
                if SpreadsheetImportProvenance.query.filter_by(athlete_id=athlete.id, semantic_fingerprint=semantic).first():
                    duplicates += 1
                    continue
                if log is None:
                    occurred = datetime.fromisoformat(row["date_value"]) if row["date_value"] else datetime.now(UTC).replace(tzinfo=None)
                    log = TrainingSessionLog(organisation_id=organisation_id, athlete_id=athlete.id, session_id=None,
                        session_name=row["session"] or "Imported session", block_name="Imported history", week_name=row["week"] or "Imported",
                        status="completed", started_at=occurred, completed_at=occurred)
                    db.session.add(log); db.session.flush(); logs[group] = log
                exercise_position = row["source_row"]
                result = TrainingSetResult(organisation_id=organisation_id, session_log_id=log.id, exercise_name=row["exercise"][:160],
                    exercise_position=exercise_position, set_order=set_no, is_extra=False, prescribed_reps=str(row["reps_value"]) if row["reps_value"] is not None else None,
                    completed=True, skipped=False, actual_load_kg=row["load_value"], actual_reps=row["reps_value"], actual_rpe=row["rpe_value"], athlete_note=row["notes"][:500] or None)
                db.session.add(result); db.session.flush()
                db.session.add(SpreadsheetImportProvenance(organisation_id=organisation_id, athlete_id=athlete.id, batch_id=batch.id,
                    training_set_result_id=result.id, source_sheet=data["sheet"]["name"], source_row=row["source_row"], semantic_fingerprint=semantic,
                    semantic_values={key: row.get(key) for key in ("athlete", "date_value", "week", "session", "exercise", "sets_value", "reps_value", "load_value", "rpe_value", "notes", "variation", "lift_family")} | {"set_number": set_no}))
                imported += 1
        batch.rows_imported, batch.rows_skipped_duplicate, batch.rows_rejected = imported, duplicates, rejected
        db.session.commit()
    except Exception:
        db.session.rollback(); record_spreadsheet_import("failed"); raise
    record_spreadsheet_import("completed", imported=imported, skipped_duplicate=duplicates, rejected=rejected)
    return render_template("spreadsheet_import/result.html", athlete=athlete, batch=batch)
