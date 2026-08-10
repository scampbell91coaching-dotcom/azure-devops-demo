"""Structural regression corpus for representative V7.9 programmes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.exercise_library import Exercise
from portal.models.programming import TrainingBlock


GOLDEN_PATH = Path(__file__).parent / "fixtures" / "v79_golden_programmes.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]


def _create_app():
    return create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )


def _proposal_fields(response):
    proposal_id = re.search(rb'name="proposal_id" value="(\d+)"', response.data)
    integrity = re.search(
        rb'name="proposal_integrity" value="([0-9a-f]+)"', response.data
    )
    assert proposal_id and integrity
    return {
        "proposal_id": proposal_id.group(1).decode(),
        "proposal_integrity": integrity.group(1).decode(),
    }


def _seed_case(app, case):
    with app.app_context():
        athlete = Athlete(
            first_name="Golden", last_name="Lifter", email="golden@example.com"
        )
        db.session.add(athlete)
        for item in GOLDEN["catalogue"]:
            db.session.add(
                Exercise(
                    name=item["name"],
                    movement="accessory",
                    category="assistance",
                    accessory_suitable=True,
                    auto_select=item.get("auto_select", False),
                    lift_relevance='["all"]',
                    training_phases='["all"]',
                    coach_priority=item.get("priority", 0),
                    default_sets=item["sets"],
                    default_reps=item["reps"],
                )
            )
        db.session.commit()
        ids = {row.name: row.id for row in Exercise.query.all()}
        return athlete.id, ids


def _generate(app, case, athlete_id, exercise_ids):
    squat, bench, deadlift = case["frequencies"]
    form = {
        "athlete_id": athlete_id,
        "name": f"Golden: {case['id']}",
        "week_count": 1,
        "training_days": 3,
        "split": "POWERLIFTING_3",
        "goal": case["goal"],
        "squat_frequency": squat,
        "bench_frequency": bench,
        "deadlift_frequency": deadlift,
        "deadlift_style": "conventional",
        "accessory_mode": case["accessory_mode"],
        "accessory_volume": case["accessory_volume"],
    }
    if case.get("pinned"):
        form["accessory_exercise_id"] = [
            exercise_ids[name] for name in case["pinned"]
        ]
    client = app.test_client()
    preview = client.post("/programming/factory/preview", data=form)
    assert preview.status_code == 200
    accepted = client.post("/programming/factory", data=_proposal_fields(preview))
    assert accepted.status_code == 302


def _prescription_shape(item):
    return {
        "name": item.exercise_name,
        "position": item.position,
        "sets": item.sets,
        "reps": item.reps,
        "rpe": item.rpe,
        "provenance": item.provenance,
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_golden_programme_structure_survives_preview_and_persistence(case):
    app = _create_app()
    athlete_id, exercise_ids = _seed_case(app, case)
    _generate(app, case, athlete_id, exercise_ids)

    with app.app_context():
        block_id = TrainingBlock.query.one().id
        db.session.expire_all()
        sessions = db.session.get(TrainingBlock, block_id).weeks[0].sessions
        assert len(sessions) == len(case["expected"])

        catalogue = {item["name"]: item for item in GOLDEN["catalogue"]}
        start_rpe = {"hypertrophy": 6.0, "development": 6.0,
                     "strength": 6.5, "peaking": 7.0}[case["goal"]]
        main_reps, secondary_reps = {
            "hypertrophy": ("8", "10"),
            "development": ("5", "8"),
            "strength": ("3", "6"),
            "peaking": ("1", "4"),
        }[case["goal"]]
        main_names = {
            "squat": "Competition Squat",
            "bench": "Competition Bench Press",
            "deadlift": "Conventional Deadlift",
        }

        for session, expected in zip(sessions, case["expected"]):
            # Slot identity/order is independent of assistance row ordering.
            assert [slot.position for slot in session.lift_slots] == list(
                range(1, len(expected["lifts"]) + 1)
            )
            assert [slot.lift_family for slot in session.lift_slots] == expected["lifts"]

            main = session.prescriptions[: len(expected["lifts"])]
            assistance = session.prescriptions[len(expected["lifts"]):]
            assert [item.exercise_name for item in main] == [
                main_names[family] for family in expected["lifts"]
            ]
            assert [item.exercise_name for item in assistance] == expected["accessories"]
            assert [item.position for item in session.prescriptions] == list(
                range(1, len(session.prescriptions) + 1)
            )

            assert [_prescription_shape(item) for item in main] == [
                {
                    "name": main_names[family],
                    "position": position,
                    "sets": 1 if case["goal"] == "peaking" and position == 1
                    else (4 if case["goal"] == "strength" and position == 1 else 3),
                    "reps": main_reps if position == 1 else secondary_reps,
                    "rpe": start_rpe if position == 1 else start_rpe + 0.5,
                    "provenance": "generated",
                }
                for position, family in enumerate(expected["lifts"], start=1)
            ]
            assert [
                (item.sets, item.reps, item.rpe, item.provenance, item.lift_slot_id)
                for item in assistance
            ] == [
                (
                    catalogue[name]["sets"],
                    catalogue[name]["reps"],
                    start_rpe + 0.5,
                    "coach_selected" if case.get("pinned") else "generated",
                    None,
                )
                for name in expected["accessories"]
            ]


def test_golden_corpus_covers_required_representative_shapes():
    by_id = {case["id"]: case for case in CASES}
    assert set(by_id) == {
        "low_accessory", "moderate_accessory", "high_accessory_over_three",
        "zero_assistance", "competition_oriented", "manual_pinned_assistance",
    }
    assert max(
        len(session["accessories"])
        for session in by_id["high_accessory_over_three"]["expected"]
    ) > 3
    assert all(
        not session["accessories"]
        for session in by_id["zero_assistance"]["expected"]
    )
