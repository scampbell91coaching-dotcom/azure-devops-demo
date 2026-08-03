import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)


def _app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _week(app):
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        block = TrainingBlock(athlete=athlete, name="Prep")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        first = TrainingSession(week=week, name="Lower", position=1)
        second = TrainingSession(week=week, name="Upper", position=2)
        squat = ExercisePrescription(
            session=first,
            exercise_name="Squat",
            position=1,
            prescription_type="rpe",
            sets=3,
            reps="5",
            rpe=7,
        )
        db.session.add_all([athlete, block, week, first, second, squat])
        db.session.commit()
        return week.id, first.id, squat.id


def test_week_page_renders_ordered_editor_and_lifecycle_controls():
    app = _app()
    week_id, _, _ = _week(app)

    response = app.test_client().get(f"/programming/weeks/{week_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("Lower") < html.index("Upper")
    assert "1. Squat" in html
    assert "Duplicate week" in html
    assert "Extend block" in html
    assert "Delete week" in html
    for label in (
        "RPE",
        "Fixed load",
        "Load cap",
        "AMRAP",
        "Rep range",
        "Target single",
    ):
        assert label in html


@pytest.mark.parametrize(
    ("mode", "data", "field", "expected"),
    [
        ("rpe", {"sets": "3", "reps": "5", "rpe": "8"}, "rpe", 8),
        (
            "fixed_load",
            {"sets": "3", "reps": "5", "load_kg": "100"},
            "load_kg",
            100,
        ),
        (
            "load_capped",
            {"sets": "3", "reps": "5", "load_cap_kg": "120"},
            "load_cap_kg",
            120,
        ),
        ("amrap", {"sets": "1", "reps": "8+", "rpe_cap": "9"}, "amrap", True),
        (
            "rep_range",
            {"sets": "3", "reps_min": "8", "reps_max": "12"},
            "reps_max",
            12,
        ),
        (
            "single_target",
            {"target_reps": "1", "target_load_kg": "180", "target_rpe": "8"},
            "target_load_kg",
            180,
        ),
    ],
)
def test_adds_every_prescription_mode_from_week_editor(mode, data, field, expected):
    app = _app()
    week_id, session_id, _ = _week(app)
    form = {
        "week_editor": "1",
        "exercise_name": f"Exercise {mode}",
        "prescription_type": mode,
        "tempo": "31X0",
        "rest_seconds": "120",
        "notes": "Coach note",
        **data,
    }

    response = app.test_client().post(
        f"/programming/sessions/{session_id}/prescriptions", data=form
    )

    assert response.status_code == 302
    assert response.location.endswith(
        f"/programming/weeks/{week_id}#session-{session_id}"
    )
    with app.app_context():
        item = ExercisePrescription.query.filter_by(
            exercise_name=f"Exercise {mode}"
        ).one()
        assert item.position == 2
        assert item.prescription_type == mode
        assert getattr(item, field) == expected
        assert item.tempo == "31X0"
        assert item.rest_seconds == 120
        assert item.notes == "Coach note"


def test_edits_then_deletes_prescription_and_preserves_order():
    app = _app()
    _, session_id, first_id = _week(app)
    client = app.test_client()
    client.post(
        f"/programming/sessions/{session_id}/prescriptions",
        data={"exercise_name": "Bench", "sets": "3", "reps": "8"},
    )
    with app.app_context():
        second_id = ExercisePrescription.query.filter_by(exercise_name="Bench").one().id

    response = client.post(
        f"/programming/prescriptions/{first_id}",
        data={
            "week_editor": "1",
            "exercise_name": "Paused squat",
            "prescription_type": "rep_range",
            "sets": "4",
            "reps_min": "4",
            "reps_max": "6",
            "tempo": "31X0",
            "rest_seconds": "180",
            "notes": "Stay tight",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        edited = db.session.get(ExercisePrescription, first_id)
        assert edited is not None
        assert edited.exercise_name == "Paused squat"
        assert edited.prescription_type == "rep_range"
        assert (edited.sets, edited.reps_min, edited.reps_max) == (4, 4, 6)
        assert edited.rpe is None
        assert edited.tempo == "31X0"
        assert edited.rest_seconds == 180
        assert edited.notes == "Stay tight"

    client.post(f"/programming/prescriptions/{first_id}/delete")

    with app.app_context():
        assert db.session.get(ExercisePrescription, first_id) is None
        remaining = db.session.get(ExercisePrescription, second_id)
        assert remaining is not None
        assert remaining.position == 1
