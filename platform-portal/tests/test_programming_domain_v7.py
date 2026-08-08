from __future__ import annotations

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.exercise_library import Exercise
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.programming_services.lift_slots import create as create_lift_slot


def app_with_session():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "v7-tests",
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        athlete = Athlete(first_name="Test", last_name="Lifter", email="v7@test.local")
        block = TrainingBlock(athlete=athlete, name="V7")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Day 1", position=1)
        db.session.add(session)
        db.session.commit()
    return app


def exercise(name: str, family: str) -> Exercise:
    item = Exercise(
        name=name,
        movement=family,
        category="competition" if name.startswith("Competition") else "variation",
        fatigue_rating=3,
        lift_family=family,
    )
    db.session.add(item)
    db.session.flush()
    return item


def test_top_set_only_single_rpe_and_optional_load_reload():
    app = app_with_session()
    with app.app_context():
        squat = exercise("Competition Squat", "squat")
        slot = create_lift_slot(
            TrainingSession.query.one(),
            lift_family="squat",
            top_exercise=squat,
            top_sets=1,
            top_reps="3",
            top_rpe=6,
        )
        db.session.commit()
        slot_id = slot.id
        db.session.expire_all()
        reloaded = db.session.get(ProgrammingLiftSlot, slot_id)
        assert reloaded.lift_family == "squat"
        assert len(reloaded.prescriptions) == 1
        top = reloaded.prescriptions[0]
        assert top.slot_role == "top_set"
        assert top.summary == "1 x 3 @ RPE 6"
        assert top.load_kg is None


@pytest.mark.parametrize("variation", [False, True])
def test_top_and_same_family_back_off_share_one_slot(variation):
    app = app_with_session()
    with app.app_context():
        squat = exercise("Competition Squat", "squat")
        pause = exercise("Pause Squat", "squat")
        slot = create_lift_slot(
            TrainingSession.query.one(),
            lift_family="squat",
            top_exercise=squat,
            top_sets=1,
            top_reps="3",
            top_rpe_min=5,
            top_rpe_max=6,
            back_off_exercise=pause if variation else None,
            back_off_sets=3,
            back_off_reps="6",
            back_off_rpe=6,
        )
        db.session.commit()
        assert len(slot.prescriptions) == 2
        assert [row.slot_role for row in slot.prescriptions] == [
            "top_set",
            "back_off",
        ]
        assert slot.prescriptions[0].summary == "1 x 3 @ RPE 5-6"
        assert slot.prescriptions[1].exercise_name == (
            "Pause Squat" if variation else "Competition Squat"
        )
        assert slot.session.week.lift_slot_frequencies()["squat"] == 1


def test_cross_family_back_off_is_rejected():
    app = app_with_session()
    with app.app_context():
        squat = exercise("Competition Squat", "squat")
        bench = exercise("Pause Bench", "bench")
        with pytest.raises(
            ValueError, match="back-off exercise must belong to the squat"
        ):
            create_lift_slot(
                TrainingSession.query.one(),
                lift_family="squat",
                top_exercise=squat,
                top_sets=1,
                top_reps="3",
                top_rpe=6,
                back_off_exercise=bench,
                back_off_sets=3,
                back_off_reps="6",
                back_off_rpe=6,
            )


def test_bounded_rpe_requires_ordered_complete_bounds():
    item = ExercisePrescription(
        exercise_name="Squat",
        position=1,
        prescription_type="rpe",
        sets=1,
        reps="3",
        rpe_min=5,
        rpe_max=6,
    )
    item.validate()
    item.rpe_max = None
    with pytest.raises(ValueError, match="provided together"):
        item.validate()


def test_weekly_frequency_counts_slots_not_prescriptions():
    app = app_with_session()
    with app.app_context():
        week = TrainingWeek.query.one()
        session = week.sessions[0]
        lifts = {
            "squat": exercise("Competition Squat", "squat"),
            "bench": exercise("Competition Bench", "bench"),
            "deadlift": exercise("Competition Deadlift", "deadlift"),
        }
        for family, count in {"squat": 2, "bench": 3, "deadlift": 1}.items():
            for number in range(count):
                target_session = session
                if number:
                    target_session = TrainingSession(
                        week=week,
                        name=f"{family} {number}",
                        position=len(week.sessions) + 1,
                    )
                    db.session.add(target_session)
                create_lift_slot(
                    target_session,
                    lift_family=family,
                    top_exercise=lifts[family],
                    top_sets=1,
                    top_reps="3",
                    top_rpe=6,
                    back_off_sets=2,
                    back_off_reps="5",
                    back_off_rpe=6,
                )
        db.session.commit()
        assert ExercisePrescription.query.count() == 12
        assert ProgrammingLiftSlot.query.count() == 6
        assert week.lift_slot_frequencies() == {
            "bench": 3,
            "deadlift": 1,
            "squat": 2,
        }


def test_assistance_has_no_slot_and_preserves_provenance_and_order():
    app = app_with_session()
    with app.app_context():
        session = TrainingSession.query.one()
        assistance = (
            ("Row", "generated"),
            ("Triceps", "coach_selected"),
            ("Curl", "coach_authored"),
        )
        for position, (name, provenance) in enumerate(assistance, 1):
            db.session.add(
                ExercisePrescription(
                    session=session,
                    exercise_name=name,
                    position=position,
                    sets=2,
                    reps="10",
                    provenance=provenance,
                )
            )
        db.session.commit()
        db.session.expire_all()
        rows = TrainingSession.query.one().prescriptions
        assert [
            (row.exercise_name, row.provenance, row.lift_slot_id) for row in rows
        ] == [
            ("Row", "generated", None),
            ("Triceps", "coach_selected", None),
            ("Curl", "coach_authored", None),
        ]
