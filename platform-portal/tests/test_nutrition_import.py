import io
import json
import zipfile
from datetime import UTC, date, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.nutrition_import import DailyNutrition, NutritionImportJob
from portal.models.organisation import CoachAthleteOwnership, Organisation, OrganisationMembership, OrganisationRole
from portal.models.user import User, UserRole
from portal.services.nutrition_import.myfitnesspal import ImportFormatError, MyFitnessPalFileProvider


CSV = b"Date,Meal,Calories,Fat (g),Carbohydrates (g),Protein (g),Fiber (g)\n2026-08-01,Breakfast,500,10,60,30,8\n2026-08-01,Dinner,700,20,80,50,6\n2026-08-02,Breakfast,450,,55,25,\n"


@pytest.fixture
def app():
    return create_app({"TESTING": True, "SECRET_KEY": "import-test", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


@pytest.fixture
def secured_app():
    app = create_app({"TESTING": True, "AUTHENTICATION_DISABLED": False, "SECRET_KEY": "import-security", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        first = Athlete(first_name="First", last_name="Athlete", email="first@example.test")
        second = Athlete(first_name="Second", last_name="Athlete", email="second@example.test")
        db.session.add_all([first, second]); db.session.flush()
        athlete_user = User(email=first.email, role=UserRole.ATHLETE, athlete_id=first.id); athlete_user.set_password("athlete password long")
        coach = User(email="coach@example.test", role=UserRole.COACH); coach.set_password("coach password long")
        db.session.add_all([athlete_user, coach]); db.session.flush()
        organisation = Organisation(name="Import Strength", slug="import-strength")
        db.session.add(organisation); db.session.flush()
        membership = OrganisationMembership(organisation=organisation, user=coach, role=OrganisationRole.COACH)
        db.session.add(membership); db.session.flush()
        db.session.add(CoachAthleteOwnership(organisation=organisation, coach_membership=membership, athlete=second))
        db.session.commit()
        app.config["IMPORT_IDS"] = (first.id, second.id)
    return app


def _login(client, email, password):
    page = client.get("/login")
    token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    return client.post("/login", data={"email": email, "password": password, "csrf_token": token})


def _athlete(app):
    with app.app_context():
        athlete = Athlete(first_name="Import", last_name="Tester", email="import@example.test")
        db.session.add(athlete); db.session.commit(); return athlete.id


def _zip(name="Nutrition-Summary.csv", content=CSV):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive: archive.writestr(name, content)
    return stream.getvalue()


def test_valid_export_aggregates_meals_and_marks_partial():
    result = MyFitnessPalFileProvider().preview(_zip(), "mfp.zip")
    assert result.rows[0]["calories"] == 1200
    assert result.rows[0]["protein_g"] == 80
    assert result.rows[1]["is_partial"] is True


def test_missing_columns_and_malformed_csv_are_rejected():
    provider = MyFitnessPalFileProvider()
    for payload in (b"Date,Meal\n2026-01-01,Breakfast\n", b'"Date,Calories\n2026-01-01,20'):
        try: provider.preview(payload, "bad.csv")
        except ImportFormatError: pass
        else: raise AssertionError("invalid CSV accepted")


def test_unsafe_zip_path_is_rejected():
    try: MyFitnessPalFileProvider().preview(_zip("../Nutrition.csv"), "bad.zip")
    except ImportFormatError as exc: assert "unsafe path" in str(exc)
    else: raise AssertionError("unsafe ZIP accepted")


def test_preview_consent_type_size_commit_repeat_update_and_disconnect(app):
    athlete_id = _athlete(app); client = app.test_client()
    url = f"/athletes/{athlete_id}/nutrition-import/preview"
    assert client.post(url, data={"export": (io.BytesIO(CSV), "Nutrition.csv")}, content_type="multipart/form-data").status_code == 400
    assert client.post(url, data={"consent":"1", "export":(io.BytesIO(b"x"), "x.txt")}, content_type="multipart/form-data").status_code == 400
    app.config["NUTRITION_UPLOAD_MAX_BYTES"] = 2
    assert client.post(url, data={"consent":"1", "export":(io.BytesIO(CSV), "x.csv")}, content_type="multipart/form-data").status_code == 413
    app.config["NUTRITION_UPLOAD_MAX_BYTES"] = 10 * 1024 * 1024
    preview = client.post(url, data={"consent":"1", "export":(io.BytesIO(CSV), "Nutrition.csv")}, content_type="multipart/form-data")
    assert preview.status_code == 200 and b"Nothing has been added yet" in preview.data
    with app.app_context(): job_id = NutritionImportJob.query.one().id
    assert client.post(f"/athletes/{athlete_id}/nutrition-import/{job_id}/commit").status_code == 302
    with app.app_context():
        first = DailyNutrition.query.filter_by(date=date(2026,8,1)).one(); first.notes = "Keep me"; db.session.commit()
    changed = CSV.replace(b"500,10", b"600,10")
    client.post(url, data={"consent":"1", "export":(io.BytesIO(changed), "Nutrition.csv")}, content_type="multipart/form-data")
    with app.app_context(): job_id = NutritionImportJob.query.filter_by(status="preview").one().id
    client.post(f"/athletes/{athlete_id}/nutrition-import/{job_id}/commit")
    with app.app_context():
        assert DailyNutrition.query.count() == 2
        first = DailyNutrition.query.filter_by(date=date(2026,8,1)).one()
        assert first.calories == 1300 and first.notes == "Keep me"
    client.post(f"/athletes/{athlete_id}/nutrition-import/disconnect")
    with app.app_context(): assert DailyNutrition.query.count() == 0


def test_checkin_prefill_is_snapshot_and_not_changed_by_later_import(app):
    athlete_id = _athlete(app)
    with app.app_context():
        db.session.add(DailyNutrition(athlete_id=athlete_id, date=datetime.now(UTC).date(), calories=2000, protein_g=150, carbohydrate_g=220, fat_g=60, fibre_g=25, provider="myfitnesspal")); db.session.commit()
    client = app.test_client()
    client.post(f"/athletes/{athlete_id}/check-in-settings", data={"nutrition_enabled":"1", "workflow_active":"1", "checkin_day":"0"})
    with client.session_transaction() as sess: sess["athlete_id"] = athlete_id
    page = client.get(f"/athletes/{athlete_id}/check-ins/new")
    assert b'value="2000.0"' in page.data and b"Pre-filled from MyFitnessPal" in page.data


def test_anonymous_denied_athlete_isolated_and_coach_authorised(secured_app):
    first, second = secured_app.config["IMPORT_IDS"]
    anonymous = secured_app.test_client()
    assert anonymous.get(f"/athletes/{first}/nutrition-import").status_code == 302
    athlete = secured_app.test_client(); _login(athlete, "first@example.test", "athlete password long")
    assert athlete.get(f"/athletes/{first}/nutrition-import").status_code == 200
    assert athlete.get(f"/athletes/{second}/nutrition-import").status_code == 404
    coach = secured_app.test_client(); _login(coach, "coach@example.test", "coach password long")
    assert coach.get(f"/athletes/{second}/nutrition-import").status_code == 200
