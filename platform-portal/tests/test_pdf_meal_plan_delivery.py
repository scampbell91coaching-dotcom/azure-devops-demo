from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import time

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.client_service import ClientServiceChange
from portal.models.meal_plan import PdfMealPlan
from portal.models.organisation import CoachAthleteOwnership, Organisation, OrganisationMembership
from portal.models.user import User


PDF_ONE = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
PDF_TWO = b"%PDF-1.4\n2 0 obj<< /Type /Catalog >>endobj\n%%EOF\n"


def _app(tmp_path):
    return create_app({
        "TESTING": True, "AUTHENTICATION_DISABLED": False,
        "SECRET_KEY": "pdf-delivery-test",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'pdf-plans.db'}",
        "MEAL_PLAN_PDF_MAX_BYTES": 1024,
    })


def _seed(app):
    with app.app_context():
        coaches = [User(email=f"coach-{n}@test", role="coach", active=True) for n in (1, 2)]
        athletes = [Athlete(first_name="Power", last_name=f"Lifter {n}", email=f"athlete-{n}@test") for n in (1, 2)]
        db.session.add_all(coaches + athletes)
        db.session.flush()
        athlete_users = [
            User(email=f"login-{n + 1}@test", role="athlete", athlete_id=athletes[n].id, active=True)
            for n in range(2)
        ]
        db.session.add_all(athlete_users)
        organisations = [Organisation(name=f"Organisation {n}", slug=f"org-{n}") for n in (1, 2)]
        db.session.add_all(organisations)
        db.session.flush()
        memberships = [OrganisationMembership(organisation_id=organisations[n].id, user_id=coaches[n].id, role="coach") for n in range(2)]
        db.session.add_all(memberships)
        db.session.flush()
        for n in range(2):
            db.session.add(CoachAthleteOwnership(organisation_id=organisations[n].id, coach_membership_id=memberships[n].id, athlete_id=athletes[n].id))
            db.session.add(ClientServiceChange(athlete_id=athletes[n].id, service="nutrition", value="yes", effective_at=datetime(2026, 1, 1), changed_by_user_id=coaches[n].id))
        db.session.commit()
        return [(coaches[n].id, athletes[n].id, athlete_users[n].id, organisations[n].id) for n in range(2)]


def _login(client, user_id, *, organisation_id=None):
    with client.session_transaction() as session:
        session.clear()
        session.update(user_id=user_id, authenticated_at=time.time(), csrf_token="token")
        if organisation_id is not None:
            session["organisation_id"] = organisation_id


def _upload(client, athlete_id, payload, title):
    return client.post("/coach/pdf-meal-plans", data={
        "csrf_token": "token", "athlete_id": str(athlete_id),
        "effective_from": "2026-08-01", "title": title,
        "pdf": (BytesIO(payload), "plan.pdf", "application/pdf"),
    })


def test_pdf_revisions_preserve_exact_bytes_hash_history_and_immutability(tmp_path):
    app = _app(tmp_path)
    (coach_id, athlete_id, athlete_user_id, organisation_id), _ = _seed(app)
    client = app.test_client()
    _login(client, coach_id, organisation_id=organisation_id)
    assert _upload(client, athlete_id, PDF_ONE, "Meet meals").status_code == 302
    with app.app_context():
        first = PdfMealPlan.query.one()
        first_id = first.id
        assert first.pdf_bytes == PDF_ONE
        assert first.content_sha256 == sha256(PDF_ONE).hexdigest()
    assert client.post(f"/coach/pdf-meal-plans/{first_id}/publish", data={"csrf_token": "token"}).status_code == 302
    assert client.post(f"/coach/pdf-meal-plans/{first_id}/publish", data={"csrf_token": "token"}).status_code == 409
    assert _upload(client, athlete_id, PDF_TWO, "Revised meet meals").status_code == 302
    with app.app_context():
        second = PdfMealPlan.query.filter_by(revision=2).one()
        second_id = second.id
        assert PdfMealPlan.query.filter_by(revision=1).one().pdf_bytes == PDF_ONE
    assert client.post(f"/coach/pdf-meal-plans/{second_id}/publish", data={"csrf_token": "token"}).status_code == 302
    _login(client, athlete_user_id)
    page = client.get("/athlete/pdf-meal-plan")
    assert page.status_code == 200
    assert b"Revised meet meals" in page.data and b"revision 1" in page.data
    assert b'class="athlete-workspace"' in page.data
    assert b'aria-label="Athlete navigation"' in page.data
    assert b"Traditional Strength Platform" not in page.data
    download = client.get(f"/athlete/pdf-meal-plans/{first_id}/download")
    assert download.status_code == 200
    assert download.data == PDF_ONE
    assert download.headers["ETag"].strip('"') == sha256(PDF_ONE).hexdigest()


def test_pdf_coach_and_athlete_access_is_tenant_qualified(tmp_path):
    app = _app(tmp_path)
    first, second = _seed(app)
    client = app.test_client()
    _login(client, first[0], organisation_id=first[3])
    assert _upload(client, second[1], PDF_ONE, "Cross tenant").status_code == 404
    assert _upload(client, first[1], PDF_ONE, "North private").status_code == 302
    with app.app_context():
        plan = PdfMealPlan.query.one()
        plan.status = "published"
        plan.published_at = datetime.now(UTC)
        db.session.commit()
        plan_id = plan.id
    _login(client, second[2])
    assert client.get(f"/athlete/pdf-meal-plans/{plan_id}/download").status_code == 404


def test_pdf_upload_rejects_spoofed_and_oversized_content(tmp_path):
    app = _app(tmp_path)
    first, _ = _seed(app)
    client = app.test_client()
    _login(client, first[0], organisation_id=first[3])
    assert _upload(client, first[1], b"not a pdf", "Spoofed").status_code == 400
    assert _upload(client, first[1], b"%PDF-1.4\n" + b"x" * 1100 + b"%%EOF\n", "Huge").status_code == 413
    with app.app_context():
        assert PdfMealPlan.query.count() == 0
