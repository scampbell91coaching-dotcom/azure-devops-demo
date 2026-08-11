import json
from pathlib import Path

from scripts.build_exercise_catalogue import build


DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "traditional_strength_intelligence.json"
)


def test_generated_catalogue_matches_committed_asset():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 7
    assert payload["exercises"] == build()


def test_unilateral_category_has_unilateral_constraint_tag():
    records = build()

    missing = [
        record["name"]
        for record in records
        if record["category"] == "unilateral"
        and "unilateral" not in record["constraint_tags"]
    ]

    assert missing == []


def test_competition_relationships_are_complete_and_canonical():
    records = build()
    names = {record["name"] for record in records}
    roots = {
        "squat": "Competition Squat",
        "bench": "Competition Bench Press",
        "deadlift": "Competition Deadlift",
    }

    for record in records:
        if record["specificity"] == "competition":
            assert record["name"] == roots[record["lift_family"]]
            assert record["variation_of"] is None
        elif record["lift_family"] in roots:
            assert record["variation_of"] == roots[record["lift_family"]]
            assert record["variation_of"] in names
