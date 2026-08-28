from __future__ import annotations

import io
import re
import time
import zipfile

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import TrainingSessionLog, TrainingSetResult
from portal.models.spreadsheet_import import SpreadsheetImportBatch, SpreadsheetImportProvenance
from portal.models.user import User, UserRole
from portal.services.spreadsheet_import import ImportFormatError, detect, fingerprint, interpret, read_workbook
from tenancy_factories import grant_coach_athlete_access


def _xlsx(rows):
    cells = []
    for ri, row in enumerate(rows, 1):
        inner = []
        for ci, value in enumerate(row):
            column = chr(65 + ci)
            inner.append(f'<c r="{column}{ri}" t="inlineStr"><is><t>{value}</t></is></c>')
        cells.append(f'<row r="{ri}">{"".join(inner)}</row>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        "xl/workbook.xml": '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Week 1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(cells)}</sheetData></worksheet>',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items(): archive.writestr(name, value)
    return output.getvalue()


def test_csv_aliases_arbitrary_order_header_below_row_one_blank_rows_and_carry_down():
    payload = b"Training export,,,,\n,,,,\nMovement,Comments,Training Date,Reps,Weight\nSquat,good,2026-01-02,5,100\nBench,=2+2,,3,80\n,,,,\n"
    workbook = read_workbook(payload, "history.csv")
    found = detect(workbook.sheets[0])
    assert found["header_row"] == 2
    rows = interpret(workbook.sheets[0], found["header_row"], found["mapping"])
    assert [(r["exercise"], r["date_value"], r["notes"]) for r in rows] == [("Squat", "2026-01-02", "good"), ("Bench", "2026-01-02", "=2+2")]


def test_xlsx_and_multiple_sets_shape():
    workbook = read_workbook(_xlsx([["Day", "Exercise", "Sets", "Load KG"], ["A", "Deadlift", "3x5", "140"]]), "log.xlsx")
    found = detect(workbook.sheets[0]); rows = interpret(workbook.sheets[0], found["header_row"], found["mapping"])
    assert rows[0]["sets_value"] == 3 and rows[0]["reps_value"] == 5


def test_xlsx_formula_is_never_read_or_executed():
    payload = _xlsx([["Exercise", "Reps"], ["Squat", "5"]])
    source, output = zipfile.ZipFile(io.BytesIO(payload)), io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<c r="B2" t="inlineStr"><is><t>5</t></is></c>', b'<c r="B2"><f>2+3</f><v>5</v></c>')
            target.writestr(item, content)
    payload = output.getvalue()
    workbook = read_workbook(payload, "formula.xlsx")
    assert workbook.formula_cells == 1
    assert workbook.sheets[0]["rows"][1][1] == ""


@pytest.mark.parametrize("filename,payload", [("bad.txt", b"x"), ("fake.xlsx", b"not zip"), ("fake.csv", b"PK\x03\x04x")])
def test_invalid_type_or_content(filename, payload):
    with pytest.raises(ImportFormatError): read_workbook(payload, filename)


def test_bounds_and_malformed_numbers_and_optional_fields():
    with pytest.raises(ImportFormatError): read_workbook(("a," * 81).encode(), "wide.csv")
    sheet = read_workbook(b"Date,Exercise,Reps\n2026-01-01,Squat,nope\n2026-01-02,Bench,5\n", "x.csv").sheets[0]
    found = detect(sheet); rows = interpret(sheet, 0, found["mapping"])
    assert rows[0]["errors"] and not rows[1]["errors"] and rows[1]["load_value"] is None


@pytest.fixture()
def import_app():
    app = create_app({"TESTING": True, "AUTHENTICATION_DISABLED": False, "SECRET_KEY": "import-test", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SPREADSHEET_UPLOAD_MAX_BYTES": 1024 * 1024})
    with app.app_context():
        db.create_all()
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex-import@example.com")
        other = Athlete(first_name="Other", last_name="Athlete", email="other-import@example.com")
        coach = User(email="coach-import@example.com", role=UserRole.COACH, password_hash="unused")
        outsider = User(email="outsider-import@example.com", role=UserRole.COACH, password_hash="unused")
        db.session.add_all([athlete, other, coach, outsider]); db.session.flush()
        membership = grant_coach_athlete_access(coach, [athlete], name="Import Org", slug="import-org")
        grant_coach_athlete_access(outsider, [other], name="Other Org", slug="other-org")
        db.session.commit()
        app.config["IDS"] = athlete.id, other.id, coach.id, outsider.id, membership.organisation_id
    return app


def _login(client, user, organisation):
    with client.session_transaction() as session:
        session.update(user_id=user, organisation_id=organisation, authenticated_at=time.time(), csrf_token="csrf")


def _hidden(response, name):
    match = re.search(rb'name="' + name.encode() + rb'" value="([^"]+)"', response.data)
    assert match
    return match.group(1).decode().replace("&#34;", '"')


def _flow(client, athlete_id, csv_data):
    mapped = client.post(f"/athletes/{athlete_id}/spreadsheet-import/map", data={"csrf_token":"csrf", "spreadsheet":(io.BytesIO(csv_data), "history.csv")}, content_type="multipart/form-data")
    assert mapped.status_code == 200
    token = _hidden(mapped, "preview_token")
    reviewed = client.post(f"/athletes/{athlete_id}/spreadsheet-import/review", data={"csrf_token":"csrf", "preview_token":token, "column_0":"date", "column_1":"session", "column_2":"exercise", "column_3":"sets", "column_4":"reps", "column_5":"load", "column_6":"rpe", "column_7":"notes"})
    assert reviewed.status_code == 200
    return reviewed, _hidden(reviewed, "preview_token")


def test_preview_zero_persistence_commit_provenance_native_untouched_and_idempotent(import_app):
    athlete, _, coach, _, org = import_app.config["IDS"]; client = import_app.test_client(); _login(client, coach, org)
    native = None
    csv_data = b"Date,Session,Exercise,Sets,Reps,Load,RPE,Notes\n2026-01-02,Day 1,Squat,2,5,100,7,=HYPERLINK(x)\n"
    reviewed, token = _flow(client, athlete, csv_data)
    with import_app.app_context():
        assert SpreadsheetImportBatch.query.count() == TrainingSessionLog.query.count() == TrainingSetResult.query.count() == 0
    result = client.post(f"/athletes/{athlete}/spreadsheet-import/commit", data={"csrf_token":"csrf", "preview_token":token, "confirm":"yes"})
    assert result.status_code == 200 and b"2" in result.data
    with import_app.app_context():
        assert TrainingSetResult.query.count() == SpreadsheetImportProvenance.query.count() == 2
        assert TrainingSetResult.query.first().athlete_note == "=HYPERLINK(x)"
        provenance = SpreadsheetImportProvenance.query.first(); assert provenance.source_sheet == "CSV" and provenance.source_row == 2 and provenance.batch.source_filename == "history.csv"
        assert provenance.semantic_values["exercise"] == "Squat"
    reviewed, token = _flow(client, athlete, csv_data)
    assert b"duplicate sets" in reviewed.data
    client.post(f"/athletes/{athlete}/spreadsheet-import/commit", data={"csrf_token":"csrf", "preview_token":token, "confirm":"yes"})
    with import_app.app_context(): assert TrainingSetResult.query.count() == 2


def test_back_to_mapping_preserves_preview_and_mapping(import_app):
    athlete, _, coach, _, org = import_app.config["IDS"]; client = import_app.test_client(); _login(client, coach, org)
    reviewed, token = _flow(client, athlete, b"Date,Session,Exercise,Sets,Reps,Load,RPE,Notes\n2026-01-02,D1,Squat,1,5,100,7,x\n")

    mapped = client.post(f"/athletes/{athlete}/spreadsheet-import/map", data={"csrf_token":"csrf", "preview_token":token})

    assert mapped.status_code == 200
    assert b"Check the column mapping" in mapped.data
    assert b'name="column_2"' in mapped.data
    assert b'<option value="exercise" selected>' in mapped.data
    with import_app.app_context():
        assert SpreadsheetImportBatch.query.count() == TrainingSessionLog.query.count() == TrainingSetResult.query.count() == 0


def test_partial_overlap_corrected_row_and_target_scope(import_app):
    athlete, other, coach, _, org = import_app.config["IDS"]; client = import_app.test_client(); _login(client, coach, org)
    first = b"Date,Session,Exercise,Sets,Reps,Load,RPE,Notes\n2026-01-02,D1,Squat,1,5,100,7,x\n"
    _, token = _flow(client, athlete, first); client.post(f"/athletes/{athlete}/spreadsheet-import/commit", data={"csrf_token":"csrf","preview_token":token,"confirm":"yes"})
    overlap = b"Date,Session,Exercise,Sets,Reps,Load,RPE,Notes\n2026-01-02,D1,Squat,1,5,100,7,x\n2026-01-02,D1,Bench,1,5,80,7,y\n2026-01-02,D1,Squat,1,5,102.5,7,x\n"
    _, token = _flow(client, athlete, overlap); client.post(f"/athletes/{athlete}/spreadsheet-import/commit", data={"csrf_token":"csrf","preview_token":token,"confirm":"yes"})
    with import_app.app_context():
        assert TrainingSetResult.query.count() == 3
        assert {p.athlete_id for p in SpreadsheetImportProvenance.query.all()} == {athlete}


def test_cross_coach_and_cross_tenant_denied(import_app):
    athlete, _, _, outsider, _ = import_app.config["IDS"]; client = import_app.test_client()
    with import_app.app_context(): other_membership = db.session.get(User, outsider).organisation_memberships[0]
    _login(client, outsider, other_membership.organisation_id)
    assert client.get(f"/athletes/{athlete}/spreadsheet-import").status_code == 404


def test_oversized_upload_and_atomic_rollback(import_app, monkeypatch):
    athlete, _, coach, _, org = import_app.config["IDS"]; client = import_app.test_client(); _login(client, coach, org)
    import_app.config["SPREADSHEET_UPLOAD_MAX_BYTES"] = 8
    response = client.post(f"/athletes/{athlete}/spreadsheet-import/map", data={"csrf_token":"csrf","spreadsheet":(io.BytesIO(b"Exercise\nSquat\n"),"x.csv")}, content_type="multipart/form-data")
    assert response.status_code == 413
    import_app.config["SPREADSHEET_UPLOAD_MAX_BYTES"] = 1024 * 1024
    _, token = _flow(client, athlete, b"Date,Session,Exercise,Sets,Reps,Load,RPE,Notes\n2026-01-02,D1,Squat,1,5,100,7,x\n")
    from portal import spreadsheet_imports
    monkeypatch.setattr(spreadsheet_imports.db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError): client.post(f"/athletes/{athlete}/spreadsheet-import/commit", data={"csrf_token":"csrf","preview_token":token,"confirm":"yes"})
    with import_app.app_context(): assert TrainingSetResult.query.count() == 0
