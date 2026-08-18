import json
from pathlib import Path

from portal import create_app
from portal.extensions import db
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
        "aliases": ["Tempo FS", "Front Squat with Tempo"],
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
        assert json.loads(exercise.aliases) == ["Tempo FS", "Front Squat with Tempo"]
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
            "inserted": 339,
            "updated": 3,
            "skipped": 0,
            "invalid": 0,
        }
        assert Exercise.query.count() == 342
        assert exercise.catalogue_version == 7
        assert exercise.lift_family == "bench"
        assert exercise.movement_pattern == "horizontal_press"
        assert exercise.specificity == "competition"
        assert exercise.variation_of is None
        assert exercise.swap_group == "bench:horizontal_press"
        assert exercise.id == original_id
        assert exercise.competition_relevance == "direct"
        assert json.loads(exercise.aliases) == ["Comp Bench", "Competition Bench"]

        second = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        assert second.as_dict() == {
            "inserted": 0,
            "updated": 0,
            "skipped": 342,
            "invalid": 0,
        }
        assert Exercise.query.count() == 342


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


def test_import_updates_existing_catalogue_exercise():
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


def test_import_does_not_overwrite_manually_created_matching_exercise():
    app = create_test_app()
    with app.app_context():
        manual = Exercise(
            name="Cable Row",
            movement="accessory",
            category="coach custom",
            fatigue_rating=1,
            coaching_cues="Coach-maintained cue",
        )
        db.session.add(manual)
        db.session.commit()
        manual_id = manual.id

        result = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        preserved = db.session.get(Exercise, manual_id)

        assert result.invalid == 0
        assert preserved.category == "coach custom"
        assert preserved.coaching_cues == "Coach-maintained cue"
        assert preserved.catalogue_version is None
        assert Exercise.query.filter_by(name="Cable Row").count() == 1


def test_coach_edit_opts_catalogue_record_out_of_future_updates():
    app = create_test_app()
    with app.app_context():
        import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        exercise = Exercise.query.filter_by(name="Cable Row").one()
        exercise_id = exercise.id

    response = app.test_client().post(
        f"/exercise-library/{exercise_id}/edit",
        data={
            "name": "Cable Row",
            "movement": "accessory",
            "category": "coach preferred",
            "coaching_cues": "Keep this coach-authored cue",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        edited = db.session.get(Exercise, exercise_id)
        assert edited.catalogue_version is None
        result = import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        preserved = db.session.get(Exercise, exercise_id)

        assert result.skipped == 342
        assert preserved.category == "coach preferred"
        assert preserved.coaching_cues == "Keep this coach-authored cue"


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
        exercise_record(aliases=["Tempo Front Squat"]),
        exercise_record(coaching_cues=["Brace"]),
        exercise_record(coaching_cues=["Brace", "Brace"]),
        exercise_record(primary_muscles=[]),
        exercise_record(setup="Too vague"),
        exercise_record(movement="warmup", warmup_suitable=False),
        exercise_record(category="competition", competition_relevance="high"),
        exercise_record(),
        exercise_record(),
    ]

    with app.app_context():
        result = import_exercise_knowledge(malformed_records)

        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 15,
        }
        assert Exercise.query.filter_by(name="Tempo Front Squat").count() == 1


def test_v6_import_rejects_missing_or_inconsistent_swap_metadata():
    valid_v6 = exercise_record(
        lift_family="squat",
        movement_pattern="squat",
        specificity="close_variation",
        technical_purposes=["technique_variation"],
        equipment_options=["barbell"],
        constraint_tags=[],
        variation_of="Competition Squat",
        swap_group="squat:squat",
    )
    invalid = [
        {key: value for key, value in valid_v6.items() if key != "swap_group"},
        {**valid_v6, "lift_family": "bench"},
        {**valid_v6, "specificity": "competition"},
        {**valid_v6, "technical_purposes": []},
        {**valid_v6, "equipment_options": []},
    ]
    app = create_test_app()
    with app.app_context():
        result = import_exercise_knowledge(
            [*invalid, valid_v6], catalogue_version=6
        )
        assert result.as_dict() == {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "invalid": 5,
        }


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


def test_manual_create_rejects_normalised_name_and_alias_duplicates():
    app = create_test_app()
    with app.app_context():
        import_exercise_knowledge([exercise_record()])

    client = app.test_client()
    for name in ("tempo-front squat", "FRONT SQUAT WITH TEMPO"):
        response = client.post(
            "/exercise-library",
            data={"name": name, "movement": "squat"},
        )
        assert response.status_code == 409

    with app.app_context():
        assert Exercise.query.count() == 4


def test_catalogue_meets_starter_coverage_targets():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    records = payload["exercises"]

    assert payload["schema_version"] == 7
    assert 300 <= len(records) <= 400
    assert sum(item["movement"] == "squat" for item in records) >= 20
    assert sum(item["movement"] == "bench" for item in records) >= 20
    assert sum(item["movement"] == "deadlift" for item in records) >= 20
    assert sum(item["movement"] == "accessory" for item in records) >= 100
    assert sum(item["movement"] == "warmup" for item in records) >= 30
    assert len({item["name"].casefold() for item in records}) == len(records)
    assert all(item["movement_pattern"] for item in records)
    assert all(item["swap_group"] for item in records)
    assert all(item["equipment_options"] for item in records)
    assert all(item["technical_purposes"] for item in records)
    competition = [item for item in records if item["category"] == "competition"]
    assert {item["name"] for item in competition} == {
        "Competition Squat",
        "Competition Bench Press",
        "Competition Deadlift",
    }
    assert all(item["lift_family"] == item["movement"] for item in competition)


def test_catalogue_taxonomy_has_resolved_roots_and_no_false_lift_family_matches():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    records = payload["exercises"]
    by_name = {item["name"]: item for item in records}

    for item in records:
        root_name = item["variation_of"]
        if root_name is not None:
            assert root_name in by_name
            assert root_name != item["name"]
            assert by_name[root_name]["specificity"] == "competition"
            assert by_name[root_name]["lift_family"] == item["lift_family"]
        if item["lift_family"] == "none":
            assert root_name is None

    for name in {
        "Machine Chest Press",
        "Push-Up",
        "Good Morning",
        "Barbell Hip Thrust",
        "Glute Bridge",
        "45-Degree Back Extension",
        "Reverse Hyperextension",
    }:
        item = by_name[name]
        assert item["lift_family"] == "none"
        assert item["specificity"] == "general"
        assert item["accessory_suitable"]


def test_catalogue_canonical_names_aliases_and_deadlift_styles_are_consistent():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    records = payload["exercises"]
    by_name = {item["name"]: item for item in records}

    assert "Competition Bench" not in by_name
    assert "Competition Bench" in by_name["Competition Bench Press"]["aliases"]
    assert by_name["Conventional Deadlift"]["variation_of"] == "Competition Deadlift"
    assert by_name["Sumo Deadlift"]["variation_of"] == "Competition Deadlift"

    families = {item["family"] for item in records}
    categories = {item["category"] for item in records}
    assert {
        "Upper back",
        "Lower back",
        "GPP and carries",
        "Conditioning",
        "Strongman",
        "Rehabilitation regressions",
        "Breathing and position",
    } <= families
    assert {"conditioning", "gpp", "strongman", "regression"} <= categories


def test_production_catalogue_has_a_deliberate_auto_select_allowlist():
    records = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))["exercises"]
    enabled = [item for item in records if item.get("auto_select")]
    suitable = [item for item in records if item["accessory_suitable"]]
    assert enabled
    assert len(enabled) < len(suitable)
    assert all(item["accessory_suitable"] for item in enabled)
    assert not any(item["category"] in {
        "competition", "conditioning", "gpp", "strongman", "regression"
    } for item in enabled)


def test_representative_records_contain_specific_coaching_knowledge():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    records = {item["name"]: item for item in payload["exercises"]}

    squat = records["Competition Squat"]
    bench = records["Competition Bench Press"]
    deadlift = records["Competition Deadlift"]
    assert "hip crease" in squat["execution"]
    assert "press command" in bench["execution"]
    assert "down command" in deadlift["execution"]
    for competition_lift in (squat, bench, deadlift):
        assert competition_lift["competition_relevance"] == "direct"
        assert competition_lift["category"] == "competition"
        assert len(competition_lift["coaching_cues"]) == 3
        assert len(competition_lift["common_mistakes"]) == 3
        assert not competition_lift["warmup_suitable"]
        assert not competition_lift["accessory_suitable"]

    assert records["Barbell Row"]["aliases"] == ["Bent-Over Barbell Row"]
    assert records["Lat Pulldown"]["progressions"] == ["Pull-up"]
    assert "pelvis supported" in records["Leg Press"]["coaching_cues"][0]
    assert records["Dowel Hip Hinge"]["equipment"] == "dowel"


def test_warmup_records_are_unambiguously_labelled_and_prescribed():
    payload = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    warmups = [item for item in payload["exercises"] if item["movement"] == "warmup"]

    assert warmups
    assert all(item["category"] == "movement preparation" for item in warmups)
    assert all(item["warmup_suitable"] for item in warmups)
    assert all(not item["accessory_suitable"] for item in warmups)
    assert all(
        "controlled repetitions" in item["prescription_styles"] for item in warmups
    )


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
        "assault bike": b"Air Bike Intervals",
        "safety bar squat": b"Safety-Bar Squat",
        "upper back cable": b"Wide-Grip Cable Row",
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


def test_category_filtering_includes_only_the_selected_category():
    app = create_test_app()
    with app.app_context():
        import_exercise_knowledge_file(DEFAULT_DATA_PATH)

    response = app.test_client().get(
        "/exercise-library", query_string={"category": "strongman"}
    )

    assert response.status_code == 200
    assert b"Log Clean and Press" in response.data
    assert b"Competition Squat" not in response.data


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
