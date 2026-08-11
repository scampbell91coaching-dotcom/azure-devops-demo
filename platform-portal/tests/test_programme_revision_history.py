import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import ProgrammeRevision, TrainingBlock
from portal.models.user import User
from portal.programming_services.blocks import create
from portal.programming_services.revisions import append_revision
from portal.programming_services.sessions import create as create_session
from portal.programming_services.weeks import create as create_week


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _block(app):
    with app.app_context():
        athlete = Athlete(first_name="Ada", last_name="Lifter", email="ada@example.test")
        db.session.add(athlete)
        db.session.commit()
        return create(athlete, name="Authored strength", objective="Peak without changing intent").id


def test_revisions_append_in_order_and_preserve_authored_values(app):
    block_id = _block(app)
    with app.app_context():
        block = db.session.get(TrainingBlock, block_id)
        week = create_week(block, name="Specificity", notes="Keep exact coach note")
        create_session(week, name="Squat / Bench", day_label="Tuesday")

        revisions = ProgrammeRevision.query.order_by(ProgrammeRevision.revision_number).all()
        assert [row.revision_number for row in revisions] == [1, 2, 3]
        snapshot = revisions[-1].authored_snapshot
        assert snapshot["block"]["objective"] == "Peak without changing intent"
        assert snapshot["weeks"][0]["notes"] == "Keep exact coach note"
        assert snapshot["weeks"][0]["sessions"][0]["name"] == "Squat / Bench"


def test_explicit_reason_and_actor_are_durably_attributed(app):
    block_id = _block(app)
    with app.app_context(), app.test_request_context(
        "/programming", method="POST", data={"revision_reason": "Adjusted after technical review"}
    ):
        coach = User(email="coach@example.test", role="coach")
        db.session.add(coach)
        db.session.commit()
        from flask import g
        g.current_user = coach
        block = db.session.get(TrainingBlock, block_id)
        append_revision(block, change_type="review", summary="Reviewed programme")
        db.session.commit()
        revision = ProgrammeRevision.query.order_by(ProgrammeRevision.id.desc()).first()
        assert revision.reason == "Adjusted after technical review"
        assert revision.authored_by == "coach@example.test"
        assert revision.authored_by_user_id == coach.id


def test_revision_rows_cannot_be_updated_or_deleted(app):
    _block(app)
    with app.app_context():
        revision = ProgrammeRevision.query.one()
        revision.reason = "rewrite history"
        with pytest.raises(ValueError, match="append-only"):
            db.session.commit()
        db.session.rollback()
        revision = ProgrammeRevision.query.one()
        db.session.delete(revision)
        with pytest.raises(ValueError, match="append-only"):
            db.session.commit()


def test_block_page_shows_what_when_why_and_who(app):
    block_id = _block(app)
    response = app.test_client().get(f"/programming/blocks/{block_id}")
    assert response.status_code == 200
    assert b"Programme revision history" in response.data
    assert b"Created programme block" in response.data
    assert b"System" in response.data
