from datetime import date, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import CoachTechnicalObservation
from portal.models.external_coaching_review import ExternalCoachingReview
from portal.models.programming import TrainingSessionLog, TrainingSetResult
from portal.models.user import User, UserRole
from tenancy_factories import grant_coach_athlete_access


@pytest.fixture
def review_app():
    app = create_app({
        "TESTING": True,
        "AUTHENTICATION_DISABLED": False,
        "SECRET_KEY": "external-review-test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@review.test")
        other = Athlete(first_name="Sam", last_name="Lifter", email="sam@review.test")
        coach = User(email="coach@review.test", role=UserRole.COACH)
        coach.set_password("correct horse battery staple")
        athlete_user = User(email=athlete.email, role=UserRole.ATHLETE, athlete=athlete)
        athlete_user.set_password("correct horse battery staple")
        log = TrainingSessionLog(
            athlete=athlete, session_name="Squat day", block_name="Base", week_name="Week 1",
            status="completed", completed_at=datetime(2026, 8, 10, 12, 0),
        )
        result = TrainingSetResult(
            session_log=log, exercise_name="Back squat", exercise_position=1,
            set_order=1, completed=True,
        )
        observation = CoachTechnicalObservation(
            athlete=athlete, lift="squat", observation="Bar drifts forward",
            observed_on=date(2026, 8, 10), recorded_by="Coach",
        )
        other_log = TrainingSessionLog(
            athlete=other, session_name="Bench day", block_name="Base", week_name="Week 1",
            status="completed", completed_at=datetime(2026, 8, 10, 13, 0),
        )
        db.session.add_all([athlete, other, coach, athlete_user, log, result, observation, other_log])
        grant_coach_athlete_access(
            coach, [athlete], name="External Review Strength", slug="external-review-strength"
        )
        db.session.commit()
        app.config.update(
            ATHLETE_ID=athlete.id, LOG_ID=log.id, SET_ID=result.id,
            OBSERVATION_ID=observation.id, OTHER_LOG_ID=other_log.id,
        )
    return app


def _login(client, email="coach@review.test"):
    page = client.get("/login")
    token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    response = client.post("/login", data={
        "email": email, "password": "correct horse battery staple", "csrf_token": token,
    })
    assert response.status_code == 302
    page = client.get(response.headers["Location"])
    return page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()


def test_coach_records_outcome_with_optional_internal_links(review_app):
    client = review_app.test_client()
    token = _login(client)
    athlete_id = review_app.config["ATHLETE_ID"]
    response = client.post(f"/athletes/{athlete_id}/external-reviews", data={
        "csrf_token": token,
        "channel": "telegram",
        "reviewed_at": "2026-08-11T09:30",
        "session_log_id": str(review_app.config["LOG_ID"]),
        "set_result_id": str(review_app.config["SET_ID"]),
        "observation_id": str(review_app.config["OBSERVATION_ID"]),
        "coach_summary": "Reviewed the final squat set externally.",
        "action": "Keep load fixed and repeat next week.",
        "follow_up_required": "1",
        "external_url": "https://example.test/review/42",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("#external-reviews")

    with review_app.app_context():
        review = ExternalCoachingReview.query.one()
        assert review.channel == "whatsapp"
        assert review.reviewed_at == datetime(2026, 8, 11, 9, 30)
        assert review.session_log_id == review_app.config["LOG_ID"]
        assert review.set_result_id == review_app.config["SET_ID"]
        assert review.observation_id == review_app.config["OBSERVATION_ID"]
        assert review.follow_up_required is True
        assert review.resolved is False
        assert review.external_url == "https://example.test/review/42"

    page = client.get(f"/athletes/{athlete_id}")
    assert b"Reviewed the final squat set externally." in page.data
    assert b"Messages and media remain outside Traditional Strength." in page.data


def test_external_review_rejects_cross_athlete_reference_and_bad_url(review_app):
    client = review_app.test_client()
    token = _login(client)
    path = f"/athletes/{review_app.config['ATHLETE_ID']}/external-reviews"
    base = {
        "csrf_token": token, "reviewed_at": "2026-08-11T09:30",
        "coach_summary": "Summary", "action": "Action",
    }
    response = client.post(path, data={**base, "session_log_id": review_app.config["OTHER_LOG_ID"]})
    assert response.status_code == 404
    response = client.post(path, data={**base, "external_url": "javascript:alert(1)"})
    assert response.status_code == 400
    with review_app.app_context():
        assert ExternalCoachingReview.query.count() == 0


def test_required_outcome_fields_are_enforced(review_app):
    client = review_app.test_client()
    token = _login(client)
    response = client.post(
        f"/athletes/{review_app.config['ATHLETE_ID']}/external-reviews",
        data={"csrf_token": token, "reviewed_at": "2026-08-11T09:30", "coach_summary": "Summary"},
    )
    assert response.status_code == 400


def test_coach_can_mark_review_resolved(review_app):
    with review_app.app_context():
        review = ExternalCoachingReview(
            athlete_id=review_app.config["ATHLETE_ID"], channel="whatsapp",
            reviewed_at=datetime(2026, 8, 11, 9, 30), coach_summary="Summary",
            action="Follow up", follow_up_required=True, resolved=False,
        )
        db.session.add(review)
        db.session.commit()
        review_id = review.id
    client = review_app.test_client()
    token = _login(client)
    response = client.post(
        f"/athletes/{review_app.config['ATHLETE_ID']}/external-reviews/{review_id}/resolve",
        data={"csrf_token": token},
    )
    assert response.status_code == 302
    with review_app.app_context():
        assert db.session.get(ExternalCoachingReview, review_id).resolved is True


def test_athlete_cannot_create_or_resolve_external_review(review_app):
    client = review_app.test_client()
    token = _login(client, "alex@review.test")
    athlete_id = review_app.config["ATHLETE_ID"]
    response = client.post(f"/athletes/{athlete_id}/external-reviews", data={
        "csrf_token": token, "reviewed_at": "2026-08-11T09:30",
        "coach_summary": "Summary", "action": "Action",
    })
    assert response.status_code == 403
