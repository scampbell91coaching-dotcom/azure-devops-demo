"""Structural regression corpus for representative V7.9 programmes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteStateRecommendation
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
                    lift_relevance=json.dumps([item.get("relevance", "all")]),
                    training_phases='["all"]',
                    coach_priority=item.get("priority", 0),
                    fatigue_rating=item.get("fatigue", 3),
                    movement_pattern=item.get("pattern"),
                    swap_group=(
                        f"golden:{item['pattern']}" if item.get("pattern") else None
                    ),
                    technical_purposes=json.dumps([item["purpose"]])
                    if item.get("purpose") else None,
                    default_sets=item["sets"],
                    default_reps=item["reps"],
                    default_rpe=item.get("rpe"),
                    default_rest_seconds=item.get("rest"),
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
    proposal_fields = _proposal_fields(preview)
    with app.app_context():
        preview_days = AthleteStateRecommendation.query.one().recommendation_json[
            "preview"
        ]
    accepted = client.post("/programming/factory", data=proposal_fields)
    assert accepted.status_code == 302
    return preview_days


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
    preview_days = _generate(app, case, athlete_id, exercise_ids)

    with app.app_context():
        block_id = TrainingBlock.query.one().id
        db.session.expire_all()
        sessions = db.session.get(TrainingBlock, block_id).weeks[0].sessions
        assert len(sessions) == len(case["expected"])

        catalogue = {item["name"]: item for item in GOLDEN["catalogue"]}
        start_rpe = {"hypertrophy": 6.0, "development": 6.0,
                     "strength": 6.5, "peaking": 7.0}[case["goal"]]
        variations = {
            "squat": {
                "competition": "Competition Squat", "primary_volume": "High-Bar Back Squat",
                "secondary_strength": "Pause Squat", "overload": "Pin Squat",
            },
            "bench": {
                "competition": "Competition Bench Press", "primary_volume": "Close-Grip Bench Press",
                "secondary_strength": "Paused Bench Press", "overload": "Slingshot Bench Press",
            },
            "deadlift": {
                "competition": "Conventional Deadlift", "primary_volume": "Romanian Deadlift",
                "secondary_strength": "Paused Deadlift", "overload": "Block Pull",
            },
        }
        role_shapes = {
            "competition": ("3", 0.5, "competition practice"),
            "primary_volume": ("6", -0.5, "primary volume"),
            "secondary_strength": ("4", 0.0, "secondary strength"),
            "overload": ("2", 1.0, "overload strength"),
        }
        set_totals = {"squat": 0, "bench": 0, "deadlift": 0}

        for session, expected, preview_day in zip(
            sessions, case["expected"], preview_days
        ):
            # Slot identity/order is independent of assistance row ordering.
            assert [slot.position for slot in session.lift_slots] == list(
                range(1, len(expected["lifts"]) + 1)
            )
            assert [slot.lift_family for slot in session.lift_slots] == expected["lifts"]

            main = session.prescriptions[: len(expected["lifts"])]
            assistance = session.prescriptions[len(expected["lifts"]):]
            assert [item.exercise_name for item in main] == [
                variations[slot.lift_family][slot.exposure_role]
                for slot in session.lift_slots
            ]
            assert [item.exercise_name for item in assistance] == expected["accessories"]
            assert [item["name"] for item in preview_day["accessories"]] == expected[
                "accessories"
            ]
            assert [item.position for item in session.prescriptions] == list(
                range(1, len(session.prescriptions) + 1)
            )

            for item, slot in zip(main, session.lift_slots):
                reps, offset, purpose = role_shapes[slot.exposure_role]
                assert _prescription_shape(item) == {
                    "name": variations[slot.lift_family][slot.exposure_role],
                    "position": slot.position,
                    "sets": item.sets,
                    "reps": reps,
                    "rpe": max(1.0, min(10.0, start_rpe + offset)),
                    "provenance": "generated",
                }
                assert item.sets >= 1
                set_totals[slot.lift_family] += item.sets
                assert item.notes == purpose
            assert [
                (item.sets, item.reps, item.rpe, item.provenance, item.lift_slot_id)
                for item in assistance
            ] == [
                (
                    catalogue[name]["sets"],
                    catalogue[name]["reps"],
                    catalogue[name].get("rpe", start_rpe + 0.5),
                    "coach_selected" if case.get("pinned") else "generated",
                    None,
                )
                for name in expected["accessories"]
            ]
            if all(item["prescriptions"] for item in preview_day["accessories"]):
                assert [
                    (
                        item.exercise_name,
                        item.position,
                        item.sets,
                        item.reps,
                        item.rpe,
                        item.rest_seconds,
                        item.provenance,
                        item.notes,
                    )
                    for item in assistance
                ] == [
                    (
                        item["name"],
                        len(expected["lifts"]) + index,
                        item["prescriptions"][0]["sets"],
                        item["prescriptions"][0]["reps"],
                        item["prescriptions"][0]["rpe"],
                        item["prescriptions"][0]["rest_seconds"],
                        item["provenance"],
                        item["reason"],
                    )
                    for index, item in enumerate(
                        preview_day["accessories"], start=1
                    )
                ]

        envelope = AthleteStateRecommendation.query.one().recommendation_json[
            "volume_progression"
        ]["weeks"][0]["sbd_sets"]
        assert set_totals == envelope

        if case["accessory_mode"] == "automatic":
            planned = [
                item for day in preview_days for item in day["accessories"]
            ]
            assert len({item["name"] for item in planned}) == len(planned)
            assert len({item["purpose"] for item in planned}) == len(planned)
            assert sum(catalogue[item["name"]]["fatigue"] for item in planned) <= {
                "low": 2, "medium": 4, "high": 6,
            }[case["accessory_volume"]] * len(case["expected"])
            if case["accessory_volume"] == "low":
                assert len(planned) <= len(case["expected"])


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
