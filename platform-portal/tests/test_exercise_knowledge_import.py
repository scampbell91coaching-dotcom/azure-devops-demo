import json
from pathlib import Path

from portal import create_app
from portal.models.exercise_library import Exercise
from portal.services.exercise_knowledge_import import (
    DEFAULT_DATA_PATH,
    import_exercise_knowledge,
    import_exercise_knowledge_file,
)


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def exercise_record(**overrides):
    record = {
        "name": "Tempo Front Squat",
        "movement": "squat",
        "family": "Squat",
        "category": "variation",
        "equipment": "barbell",
        "fatigue_rating": 4,
        "occurrences": 12,
        "aliases": ["Tempo FS", "Tempo Front Squat"],
    }
    record.update(overrides)
    return record


def test_first_import_persists_all_supported_knowledge_fields():
    app = create_test_app()

    with app.app_context():
        result = import_exercise_knowledge([exercise_record()])
        exercise = Exercise.query.filter_by(name="Tempo Front Squat").one()

        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 0,
        }
        assert exercise.movement == "squat"
        assert exercise.family == "Squat"
        assert exercise.category == "variation"
        assert exercise.equipment == "barbell"
        assert exercise.fatigue_rating == 4
        assert exercise.occurrence_count == 12
        assert json.loads(exercise.aliases) == ["Tempo FS", "Tempo Front Squat"]


def test_bundled_production_dataset_imports_cleanly():
    app = create_test_app()

    with app.app_context():
        result = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        exercise = Exercise.query.filter_by(name="Bench Press").one()

        assert result.as_dict() == {
            "inserted": 1291,
            "updated": 3,
            "skipped": 0,
            "invalid": 0,
        }
        assert Exercise.query.count() == 1294
        assert exercise.occurrence_count == 3718
        assert json.loads(exercise.aliases) == ["BENCH PRESS", "Bench"]


def test_repeated_import_is_idempotent():
    app = create_test_app()
    records = [exercise_record()]

    with app.app_context():
        import_exercise_knowledge(records)
        result = import_exercise_knowledge(records)

        assert result.as_dict() == {
            "inserted": 0,
            "updated": 0,
            "skipped": 1,
            "invalid": 0,
        }
        assert Exercise.query.filter_by(name="Tempo Front Squat").count() == 1


def test_import_updates_existing_canonical_exercise():
    app = create_test_app()

    with app.app_context():
        import_exercise_knowledge([exercise_record()])
        result = import_exercise_knowledge(
            [exercise_record(occurrences=42, aliases=["Front Squat Tempo"])]
        )
        exercise = Exercise.query.filter_by(name="Tempo Front Squat").one()

        assert result.as_dict() == {
            "inserted": 0,
            "updated": 1,
            "skipped": 0,
            "invalid": 0,
        }
        assert exercise.occurrence_count == 42
        assert json.loads(exercise.aliases) == ["Front Squat Tempo"]


def test_import_counts_malformed_records_without_persisting_them():
    app = create_test_app()
    malformed_records = [
        {},
        exercise_record(name=""),
        exercise_record(movement="snatch"),
        exercise_record(fatigue_rating=6),
        exercise_record(occurrences=-1),
        exercise_record(aliases=["Valid", 3]),
        exercise_record(),
        exercise_record(),
    ]

    with app.app_context():
        result = import_exercise_knowledge(malformed_records)

        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 7,
        }
        assert Exercise.query.filter_by(name="Tempo Front Squat").count() == 1


def test_file_import_returns_counts_and_cli_reports_them(tmp_path: Path):
    app = create_test_app()
    source = tmp_path / "exercise-knowledge.json"
    source.write_text(json.dumps({"exercises": [exercise_record()]}), encoding="utf-8")

    with app.app_context():
        result = import_exercise_knowledge_file(source)

    cli_result = app.test_cli_runner().invoke(
        args=["import-exercise-knowledge", "--path", str(source)]
    )

    assert result.as_dict()["inserted"] == 1
    assert cli_result.exit_code == 0
    assert json.loads(cli_result.output) == {
        "inserted": 0,
        "invalid": 0,
        "skipped": 1,
        "updated": 0,
    }
