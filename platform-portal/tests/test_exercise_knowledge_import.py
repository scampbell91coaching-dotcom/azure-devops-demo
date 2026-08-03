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
        "default_sets": 3,
        "default_reps": "5",
        "default_rpe": 7.0,
        "default_rest_seconds": 180,
        "occurrences": 12,
        "aliases": ["Tempo FS", "Tempo Front Squat"],
        "primary_muscles": ["quadriceps", "glutes"],
        "secondary_muscles": ["trunk"],
        "goal": "squat strength",
        "difficulty": "intermediate",
        "setup": "Set the bar securely and establish a balanced stance.",
        "execution": "Descend under control, pause, then stand evenly.",
        "coaching_cues": ["Brace", "Stay balanced"],
        "common_mistakes": ["Losing balance"],
        "regressions": ["Reduce load"],
        "progressions": ["Add load gradually"],
        "cautions": "Stop if the movement causes sharp or worsening pain.",
        "competition_relevance": "high",
        "prescription_styles": ["sets and repetitions", "RPE"],
        "rep_ranges": "3-8 reps",
        "warmup_suitable": False,
        "accessory_suitable": False,
        "active": True,
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
        assert exercise.goal == "squat strength"
        assert exercise.difficulty == "intermediate"
        assert json.loads(exercise.coaching_cues) == ["Brace", "Stay balanced"]
        assert exercise.catalogue_version == 1


def test_bundled_production_dataset_imports_cleanly():
    app = create_test_app()

    with app.app_context():
        original_id = Exercise.query.filter_by(name="Competition Bench Press").one().id
        result = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        exercise = Exercise.query.filter_by(name="Competition Bench Press").one()

        assert result.as_dict() == {
            "inserted": 273,
            "updated": 3,
            "skipped": 0,
            "invalid": 0,
        }
        assert Exercise.query.count() == 276
        assert exercise.catalogue_version == 2
        assert exercise.id == original_id
        assert exercise.competition_relevance == "direct"
        assert json.loads(exercise.aliases) == ["Comp Bench", "Competition Bench"]

        second = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        assert second.as_dict() == {
            "inserted": 0,
            "updated": 0,
            "skipped": 276,
            "invalid": 0,
        }
        assert Exercise.query.count() == 276


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
        exercise_record(active="yes"),
        exercise_record(),
        exercise_record(),
    ]

    with app.app_context():
        result = import_exercise_knowledge(malformed_records)

        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 8,
        }
        assert Exercise.query.filter_by(name="Tempo Front Squat").count() == 1


def test_alias_and_canonical_names_deduplicate_across_punctuation_and_case():
    app = create_test_app()

    with app.app_context():
        first = exercise_record(name="Close-Grip Bench Press", aliases=["CGBP"])
        duplicate = exercise_record(name="cgbp", aliases=[])
        result = import_exercise_knowledge([first, duplicate])

        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 1,
        }
        assert Exercise.query.filter_by(name="Close-Grip Bench Press").count() == 1


def test_catalogue_meets_starter_coverage_targets():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    records = payload["exercises"]

    assert payload["schema_version"] == 2
    assert 250 <= len(records) <= 350
    assert sum(item["movement"] == "squat" for item in records) >= 20
    assert sum(item["movement"] == "bench" for item in records) >= 20
    assert sum(item["movement"] == "deadlift" for item in records) >= 20
    assert sum(item["movement"] == "accessory" for item in records) >= 100
    assert sum(item["movement"] == "warmup" for item in records) >= 30
    assert len({item["name"].casefold() for item in records}) == len(records)


def test_representative_canonical_alias_muscle_and_equipment_searches_render():
    app = create_test_app()

    with app.app_context():
        import_exercise_knowledge_file(DEFAULT_DATA_PATH)

    client = app.test_client()
    expectations = {
        "Safety-Bar": b"Safety-Bar Squat",
        "RFESS": b"Bulgarian Split Squat",
        "hamstrings": b"Romanian Deadlift",
        "cable": b"Cable Row",
    }
    for query, expected_name in expectations.items():
        response = client.get("/exercise-library", query_string={"q": query})
        assert response.status_code == 200
        assert expected_name in response.data

    with app.app_context():
        exercise_id = Exercise.query.filter_by(name="Competition Squat").one().id
    detail = client.get(f"/exercise-library/{exercise_id}/edit")
    assert detail.status_code == 200
    assert b"Competition Squat" in detail.data


def test_file_import_returns_counts_and_cli_reports_them(tmp_path: Path):
    app = create_test_app()
    source = tmp_path / "exercise-knowledge.json"
    source.write_text(
        json.dumps({"schema_version": 1, "exercises": [exercise_record()]}),
        encoding="utf-8",
    )

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
