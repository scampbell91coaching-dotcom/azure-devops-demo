from sqlalchemy.exc import SQLAlchemyError

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.models.warmup import (
    WarmupAssignment,
    WarmupOverride,
    WarmupPlanSnapshot,
    WarmupProtocol,
)


def _app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _programme(app):
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        block = TrainingBlock(athlete=athlete, name="Prep")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        first = TrainingSession(
            week=week,
            name="Lower",
            day_label="Monday",
            position=1,
            notes="Heavy day",
        )
        second = TrainingSession(week=week, name="Upper", position=2)
        prescriptions = [
            ExercisePrescription(
                session=first,
                exercise_name="Squat",
                position=1,
                sets=4,
                reps="5",
                rpe=7.5,
                notes="Controlled",
            ),
            ExercisePrescription(
                session=first,
                exercise_name="Lunge",
                position=2,
                sets=3,
                reps="8/side",
                rpe=8,
                notes="Long stride",
            ),
        ]
        db.session.add_all([athlete, block, week, first, second, *prescriptions])
        db.session.commit()
        return week.id, first.id, second.id


def _ordered_sessions():
    return TrainingSession.query.order_by(TrainingSession.position).all()


def test_adds_blank_session_at_end():
    app = _app()
    week_id, _, _ = _programme(app)

    response = app.test_client().post(f"/programming/weeks/{week_id}/sessions")

    assert response.status_code == 302
    with app.app_context():
        sessions = _ordered_sessions()
        assert [(item.name, item.position) for item in sessions] == [
            ("Lower", 1),
            ("Upper", 2),
            ("Session 3", 3),
        ]
        assert sessions[-1].prescriptions == []


def test_duplicate_is_adjacent_and_preserves_order_and_programming():
    app = _app()
    _, first_id, _ = _programme(app)

    response = app.test_client().post(f"/programming/sessions/{first_id}/duplicate")

    assert response.status_code == 302
    with app.app_context():
        sessions = _ordered_sessions()
        assert [(item.name, item.position) for item in sessions] == [
            ("Lower", 1),
            ("Lower Copy", 2),
            ("Upper", 3),
        ]
        copied = sessions[1]
        assert copied.day_label == "Monday"
        assert copied.notes == "Heavy day"
        assert [
            (
                item.exercise_name,
                item.position,
                item.sets,
                item.reps,
                item.rpe,
                item.notes,
            )
            for item in copied.prescriptions
        ] == [
            ("Squat", 1, 4, "5", 7.5, "Controlled"),
            ("Lunge", 2, 3, "8/side", 8, "Long stride"),
        ]


def test_duplicate_is_independent_of_source():
    app = _app()
    _, first_id, _ = _programme(app)
    app.test_client().post(f"/programming/sessions/{first_id}/duplicate")

    with app.app_context():
        source = db.session.get(TrainingSession, first_id)
        copied = TrainingSession.query.filter_by(name="Lower Copy").one()
        assert source is not None
        copied.prescriptions[0].sets = 10
        copied.prescriptions[0].notes = "Changed"
        db.session.commit()
        db.session.refresh(source.prescriptions[0])
        assert source.prescriptions[0].sets == 4
        assert source.prescriptions[0].notes == "Controlled"


def test_duplicate_preserves_authored_warmup_intent_but_not_resolved_history():
    app = _app()
    _, first_id, _ = _programme(app)
    with app.app_context():
        source = db.session.get(TrainingSession, first_id)
        assert source is not None
        protocol = WarmupProtocol(
            stable_key="squat-prep",
            version=1,
            name="Squat preparation",
        )
        db.session.add(protocol)
        db.session.flush()
        db.session.add_all(
            [
                WarmupAssignment(
                    protocol_id=protocol.id,
                    athlete_id=source.week.block.athlete_id,
                    session_id=source.id,
                    reason="Prepare hips and competition pattern",
                ),
                WarmupOverride(
                    athlete_id=source.week.block.athlete_id,
                    session_id=source.id,
                    action="append",
                    phase=20,
                    name="Banded abduction",
                    kind="reps",
                    sets=2,
                    reps=12,
                    rest_seconds=30,
                    notes="Keep pelvis level",
                    reason="Individual preparation drill",
                ),
                WarmupPlanSnapshot(
                    athlete_id=source.week.block.athlete_id,
                    session_id=source.id,
                ),
            ]
        )
        db.session.commit()

    response = app.test_client().post(f"/programming/sessions/{first_id}/duplicate")

    assert response.status_code == 302
    with app.app_context():
        copied = TrainingSession.query.filter_by(name="Lower Copy").one()
        assignment = WarmupAssignment.query.filter_by(session_id=copied.id).one()
        assert assignment.protocol.stable_key == "squat-prep"
        assert assignment.reason == "Prepare hips and competition pattern"
        override = WarmupOverride.query.filter_by(session_id=copied.id).one()
        assert (
            override.name,
            override.sets,
            override.reps,
            override.rest_seconds,
            override.notes,
            override.reason,
        ) == (
            "Banded abduction",
            2,
            12,
            30,
            "Keep pelvis level",
            "Individual preparation drill",
        )
        assert WarmupPlanSnapshot.query.filter_by(session_id=copied.id).count() == 0


def test_insert_before_and_after_creates_blank_sessions_and_renumbers():
    app = _app()
    _, first_id, second_id = _programme(app)

    before = app.test_client().post(f"/programming/sessions/{first_id}/insert-before")
    after = app.test_client().post(f"/programming/sessions/{second_id}/insert-after")

    assert before.status_code == 302
    assert after.status_code == 302
    with app.app_context():
        sessions = _ordered_sessions()
        assert [item.position for item in sessions] == [1, 2, 3, 4]
        assert [item.name for item in sessions] == [
            "Session 1",
            "Lower",
            "Upper",
            "Session 4",
        ]
        assert sessions[0].prescriptions == []
        assert sessions[3].prescriptions == []


def test_delete_cascades_prescriptions_and_renumbers_remaining_sessions():
    app = _app()
    _, first_id, second_id = _programme(app)

    response = app.test_client().post(f"/programming/sessions/{first_id}/delete")

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(TrainingSession, first_id) is None
        assert ExercisePrescription.query.count() == 0
        remaining = db.session.get(TrainingSession, second_id)
        assert remaining is not None
        assert remaining.position == 1


def test_duplicate_rolls_back_all_changes_when_flush_fails(monkeypatch):
    app = _app()
    _, first_id, _ = _programme(app)

    with app.app_context():
        original_flush = db.session.flush

        def fail_flush(*args, **kwargs):
            raise SQLAlchemyError("forced failure")

        with monkeypatch.context() as patch:
            patch.setattr(db.session, "flush", fail_flush)
            try:
                app.test_client().post(f"/programming/sessions/{first_id}/duplicate")
            except SQLAlchemyError:
                pass
            else:
                raise AssertionError("duplicate should propagate the database failure")

        original_flush()
        sessions = _ordered_sessions()
        assert [(item.name, item.position) for item in sessions] == [
            ("Lower", 1),
            ("Upper", 2),
        ]
        assert ExercisePrescription.query.count() == 2
