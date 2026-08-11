from datetime import UTC, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.client_service import ClientServiceChange
from portal.models.nutrition_prescription import NutritionMacroPrescription
from portal.models.user import User, UserRole


@pytest.fixture
def macro_app():
    app = create_app({"TESTING": True, "AUTHENTICATION_DISABLED": False, "SECRET_KEY": "macro-test", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athlete = Athlete(first_name="Alex", last_name="Rivera", email="alex@example.test")
        other = Athlete(first_name="Other", last_name="Athlete", email="other@example.test")
        coach = User(email="coach@example.test", role=UserRole.COACH); coach.set_password("coach password long enough")
        db.session.add_all([athlete, other, coach]); db.session.flush()
        athlete_user = User(email=athlete.email, role=UserRole.ATHLETE, athlete_id=athlete.id); athlete_user.set_password("athlete password long enough")
        db.session.add_all([athlete_user, ClientServiceChange(athlete_id=athlete.id, service="nutrition", value="yes", effective_at=datetime(2026, 1, 1))])
        db.session.commit()
        app.config["MACRO_IDS"] = {"athlete": athlete.id, "other": other.id, "coach": coach.id}
    return app


def _login(client, email, password):
    page = client.get("/login")
    token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    response = client.post("/login", data={"email": email, "password": password, "csrf_token": token})
    client.get(response.headers["Location"])
    with client.session_transaction() as state:
        return response, state["csrf_token"]


def _form(token, **changes):
    values = {"csrf_token": token, "effective_from": "2026-08-01", "effective_until": "2026-08-31", "calories": "2500", "protein_g": "180", "carbohydrate_g": "300", "fat_g": "65", "fibre_g": "30", "meal_count": "4", "coach_notes": "Spread protein across meals."}
    values.update(changes)
    return values


def test_coach_assigns_and_browser_pages_show_current_history_and_variants(macro_app):
    client = macro_app.test_client(); _, token = _login(client, "coach@example.test", "coach password long enough")
    athlete_id = macro_app.config["MACRO_IDS"]["athlete"]
    response = client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token, training_calories="2700", training_protein_g="180", training_carbohydrate_g="350", training_fat_g="65"))
    assert response.status_code == 302
    page = client.get(f"/athletes/{athlete_id}/nutrition-prescriptions")
    assert b"Current prescription" in page.data and b"Prescription history" in page.data
    assert b"2500 kcal" in page.data and b"Spread protein across meals" in page.data
    with macro_app.app_context():
        row = NutritionMacroPrescription.query.one()
        assert row.training_targets["calories"] == 2700
        assert row.created_by_user_id == macro_app.config["MACRO_IDS"]["coach"]


def test_effective_dates_and_overlap_are_enforced(macro_app):
    client = macro_app.test_client(); _, token = _login(client, "coach@example.test", "coach password long enough")
    athlete_id = macro_app.config["MACRO_IDS"]["athlete"]
    assert client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token)).status_code == 302
    overlap = client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token, effective_from="2026-08-31", effective_until="2026-09-10"))
    assert overlap.status_code == 400 and b"overlaps" in overlap.data
    adjacent = client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token, effective_from="2026-09-01", effective_until="2026-09-30"))
    assert adjacent.status_code == 302


def test_entitlement_gates_assignment_but_preserves_coach_history(macro_app):
    client = macro_app.test_client(); _, token = _login(client, "coach@example.test", "coach password long enough")
    athlete_id = macro_app.config["MACRO_IDS"]["athlete"]
    assert client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token)).status_code == 302
    with macro_app.app_context():
        db.session.add(ClientServiceChange(athlete_id=athlete_id, service="nutrition", value="no", effective_at=datetime.now(UTC).replace(tzinfo=None)))
        db.session.commit()
    page = client.get(f"/athletes/{athlete_id}/nutrition-prescriptions")
    assert page.status_code == 200 and b"Existing history remains below" in page.data and b"2500 kcal" in page.data
    assert client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token, effective_from="2027-01-01")).status_code == 403


def test_athlete_sees_own_effective_targets_and_notes_only_when_entitled(macro_app):
    coach_client = macro_app.test_client(); _, token = _login(coach_client, "coach@example.test", "coach password long enough")
    athlete_id = macro_app.config["MACRO_IDS"]["athlete"]
    assert coach_client.post(f"/athletes/{athlete_id}/nutrition-prescriptions", data=_form(token, effective_from="2020-01-01", effective_until="")).status_code == 302
    athlete_client = macro_app.test_client(); _login(athlete_client, "alex@example.test", "athlete password long enough")
    page = athlete_client.get("/athlete/nutrition-targets")
    assert page.status_code == 200 and b"My nutrition targets" in page.data and b"2500 kcal" in page.data and b"Spread protein" in page.data
    assert athlete_client.get(f"/athletes/{athlete_id}/nutrition-prescriptions").status_code == 403
    with macro_app.app_context():
        db.session.add(ClientServiceChange(athlete_id=athlete_id, service="nutrition", value="no", effective_at=datetime.now(UTC).replace(tzinfo=None)))
        db.session.commit()
    assert athlete_client.get("/athlete/nutrition-targets").status_code == 404


def test_invalid_partial_variant_and_period_are_rejected(macro_app):
    client = macro_app.test_client(); _, token = _login(client, "coach@example.test", "coach password long enough")
    path = f"/athletes/{macro_app.config['MACRO_IDS']['athlete']}/nutrition-prescriptions"
    assert client.post(path, data=_form(token, training_calories="2700")).status_code == 400
    assert client.post(path, data=_form(token, effective_from="2026-09-01", effective_until="2026-08-01")).status_code == 400
