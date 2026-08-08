import re

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import TrainingBlock


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_factory_page_loads():
    app = create_test_app()

    with app.app_context():
        db.session.add(
            Athlete(
                first_name="Alex",
                last_name="Lifter",
                email="alex@example.com",
            )
        )
        db.session.commit()

    response = app.test_client().get("/programming/factory")

    assert response.status_code == 200
    assert b"Block Factory" in response.data


def test_factory_generates_complete_block():
    app = create_test_app()

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    client = app.test_client()
    preview = client.post(
        "/programming/factory/preview",
        data={
            "athlete_id": athlete_id,
            "name": "Generated Prep",
            "week_count": 3,
            "training_days": 4,
            "template_type": "SBD",
        },
    )
    proposal_id = re.search(rb'name="proposal_id" value="(\d+)"', preview.data)
    integrity = re.search(
        rb'name="proposal_integrity" value="([0-9a-f]+)"', preview.data
    )
    assert proposal_id and integrity
    response = client.post(
        "/programming/factory",
        data={
            "proposal_id": proposal_id.group(1).decode(),
            "proposal_integrity": integrity.group(1).decode(),
        },
    )

    assert response.status_code == 302

    with app.app_context():
        block = TrainingBlock.query.one()
        assert len(block.weeks) == 3
        assert sum(len(week.sessions) for week in block.weeks) == 12
