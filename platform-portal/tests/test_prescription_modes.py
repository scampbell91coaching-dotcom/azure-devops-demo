import pytest
from sqlalchemy import inspect, text

from portal import create_app
from portal.extensions import db
from portal.models.programming import (
    ExercisePrescription,
    ensure_prescription_mode_columns,
)


def test_existing_prescription_table_is_migrated_without_changing_rows():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    with app.app_context():
        db.session.execute(text("DROP TABLE exercise_prescriptions"))
        db.session.execute(
            text(
                """CREATE TABLE exercise_prescriptions (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL,
                    exercise_name VARCHAR(160) NOT NULL,
                    position INTEGER NOT NULL,
                    sets INTEGER,
                    reps VARCHAR(40),
                    load_kg FLOAT,
                    percentage FLOAT,
                    rpe FLOAT,
                    tempo VARCHAR(40),
                    rest_seconds INTEGER,
                    notes TEXT
                )"""
            )
        )
        db.session.execute(
            text(
                "INSERT INTO exercise_prescriptions "
                "(id, session_id, exercise_name, position, sets, reps, rpe) "
                "VALUES (1, 1, 'Squat', 1, 3, '5', 7)"
            )
        )
        db.session.commit()

        ensure_prescription_mode_columns()
        ensure_prescription_mode_columns()

        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("exercise_prescriptions")
        }
        assert {
            "prescription_type",
            "reps_min",
            "reps_max",
            "rpe_cap",
            "load_cap_kg",
            "target_reps",
            "target_rpe",
            "target_load_kg",
            "amrap",
        } <= columns
        row = db.session.execute(
            text("SELECT exercise_name, sets, reps, rpe FROM exercise_prescriptions")
        ).one()
        assert row == ("Squat", 3, "5", 7.0)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {"prescription_type": "rpe", "sets": 4, "reps": "5", "rpe": 8},
            "4 x 5 @ RPE 8",
        ),
        (
            {
                "prescription_type": "fixed_load",
                "sets": 3,
                "reps": "6",
                "load_kg": 100,
            },
            "3 x 6 @ 100 kg",
        ),
        (
            {
                "prescription_type": "load_capped",
                "sets": 3,
                "reps": "5",
                "load_cap_kg": 120,
            },
            "3 x 5 up to 120 kg",
        ),
        (
            {
                "prescription_type": "amrap",
                "sets": 1,
                "reps": "8+",
                "amrap": True,
                "rpe_cap": 9,
            },
            "1 x 8+ AMRAP (cap RPE 9)",
        ),
        (
            {
                "prescription_type": "rep_range",
                "sets": 3,
                "reps_min": 8,
                "reps_max": 12,
            },
            "3 x 8-12",
        ),
        (
            {
                "prescription_type": "single_target",
                "target_reps": 1,
                "target_rpe": 8,
                "target_load_kg": 180,
            },
            "Single target: 1 rep @ 180 kg @ RPE 8",
        ),
    ],
)
def test_prescription_modes_validate_and_summarise(values, expected):
    item = ExercisePrescription(exercise_name="Squat", position=1, **values)

    item.validate()

    assert item.summary == expected


@pytest.mark.parametrize(
    "values",
    [
        {"prescription_type": "unknown"},
        {"prescription_type": "rpe", "sets": 3, "reps": "5", "rpe": 11},
        {"prescription_type": "rep_range", "sets": 3, "reps_min": 12, "reps_max": 8},
        {"prescription_type": "fixed_load", "sets": 3, "reps": "5"},
        {
            "prescription_type": "load_capped",
            "sets": 3,
            "reps": "5",
            "load_cap_kg": -1,
        },
        {"prescription_type": "amrap", "sets": 1, "amrap": False},
        {"prescription_type": "single_target"},
    ],
)
def test_invalid_typed_prescriptions_are_rejected(values):
    item = ExercisePrescription(exercise_name="Squat", position=1, **values)

    with pytest.raises(ValueError):
        item.validate()


def test_legacy_prescriptions_remain_valid_and_keep_their_summary():
    item = ExercisePrescription(
        exercise_name="Squat", position=1, sets=4, reps="5", load_kg=100, rpe=7
    )

    item.validate()

    assert item.prescription_type is None
    assert item.summary == "4 x 5 100 kg @ RPE 7"


def test_model_validation_runs_when_a_typed_prescription_is_saved():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    with app.app_context():
        item = ExercisePrescription(
            session_id=1,
            exercise_name="Squat",
            position=1,
            prescription_type="rpe",
            sets=3,
            reps="5",
            rpe=12,
        )
        db.session.add(item)

        with pytest.raises(ValueError, match="rpe must be between 1 and 10"):
            db.session.commit()


def test_copy_values_preserves_new_and_legacy_fields():
    source = ExercisePrescription(
        exercise_name="Squat",
        position=2,
        prescription_type="rep_range",
        sets=3,
        reps_min=8,
        reps_max=12,
        notes="Controlled tempo",
    )

    copied = ExercisePrescription(**source.copy_values())

    assert copied.summary == "3 x 8-12"
    assert copied.notes == "Controlled tempo"
