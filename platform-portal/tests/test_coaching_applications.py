from portal import create_app
from portal.extensions import db
from portal.models.coaching_application import CoachingApplication


def create_test_app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        db.create_all()

    return app


def valid_application():
    return {
        "first_name": "Alex",
        "last_name": "Lifter",
        "email": "alex@example.com",
        "country": "United Kingdom",
        "primary_goal": "Build my total and compete next year.",
        "biggest_problem": "Training is inconsistent and fatigue piles up.",
        "coaching_expectations": "Clear feedback and individual programming.",
        "privacy_consent": "yes",
        "video_feedback_ready": "yes",
        "communication_ready": "yes",
        "minimum_term_ready": "yes",
    }


def test_application_page_loads():
    app = create_test_app()
    response = app.test_client().get("/apply")

    assert response.status_code == 200
    assert b"Apply for Coaching" in response.data
    assert b"Submit Application" in response.data


def test_valid_application_is_saved():
    app = create_test_app()
    response = app.test_client().post(
        "/apply",
        data=valid_application(),
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        saved = CoachingApplication.query.one()

        assert saved.email == "alex@example.com"
        assert saved.video_feedback_ready is True
        assert saved.status == "new"


def test_required_fields_are_validated():
    app = create_test_app()
    response = app.test_client().post("/apply", data={})

    assert response.status_code == 400
    assert b"Enter your first name" in response.data
    assert b"Tell me what you want to achieve" in response.data


def test_honeypot_submission_is_not_saved():
    app = create_test_app()
    payload = valid_application()
    payload["website"] = "https://spam.example"

    response = app.test_client().post("/apply", data=payload)

    assert response.status_code == 302

    with app.app_context():
        assert CoachingApplication.query.count() == 0
