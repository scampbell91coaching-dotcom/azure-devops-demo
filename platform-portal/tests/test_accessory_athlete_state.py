from datetime import date

import pytest

from portal import create_app
from portal.block_factory import FactoryRequest, _preview
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import (
    AthleteConstraintFlag,
    AthleteStateOverride,
    AthleteStateSignal,
    CoachTechnicalObservation,
)
from portal.models.exercise_library import Exercise
from portal.services.accessory_intelligence import AccessoryIntelligence


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with instance.app_context():
        db.create_all()
    return instance


def _athlete() -> Athlete:
    item = Athlete(first_name="State", last_name="Athlete", email="state@example.test")
    db.session.add(item)
    db.session.flush()
    return item


def _exercise(name: str, *tags: str, priority: int = 5) -> Exercise:
    return Exercise(
        name=name,
        movement="accessory",
        category="assistance",
        accessory_suitable=True,
        auto_select=True,
        coach_priority=priority,
        fatigue_rating=2,
        lift_relevance='["all"]',
        constraint_tags=str(list(tags)).replace("'", '"'),
    )


def _signal(athlete_id: int, payload: dict, *source_refs: str) -> AthleteStateSignal:
    return AthleteStateSignal(
        athlete_id=athlete_id,
        snapshot_id=f"snapshot-{payload['rule_id']}",
        signal_type="assistance_selection_rule",
        value_json=payload,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
        calculation_version="coach-authored-rules-v1",
        source_refs_json=list(source_refs),
        explanation="Explicit non-diagnostic assistance rule.",
    )


def test_left_right_observation_only_changes_ranking_through_stored_rule_metadata(app):
    with app.app_context():
        athlete = _athlete()
        left = _exercise("Left-loaded split squat", "left_hip_loaded", priority=10)
        right = _exercise("Right-loaded split squat", "right_hip_loaded", priority=1)
        observation = CoachTechnicalObservation(
            athlete=athlete,
            lift="squat",
            observation="Left hip shift seen on the ascent",
            observed_on=date(2026, 8, 10),
            recorded_by="coach@example.test",
        )
        db.session.add_all([left, right, observation])
        db.session.commit()

        # Free text, including laterality, is never interpreted by the selector.
        unchanged = AccessoryIntelligence().candidates(
            phase="development", lift_families={"squat"}, athlete_id=athlete.id,
            as_of=date(2026, 8, 12),
        )
        assert [item.exercise.name for item in unchanged] == [
            "Left-loaded split squat", "Right-loaded split squat"
        ]

        db.session.add_all([
            _signal(athlete.id, {
                "rule_id": "coach.left-hip-shift.penalty.v1",
                "effect": "penalty",
                "candidate_tags": ["left_hip_loaded"],
                "weight": 20,
                "context": {"lift_families": ["squat"]},
                "reason": "Coach chose to de-prioritise left-loaded assistance for this squat context.",
            }, f"coach_technical_observation:{observation.id}"),
            _signal(athlete.id, {
                "rule_id": "coach.left-hip-shift.preference.v1",
                "effect": "preference",
                "candidate_tags": ["right_hip_loaded"],
                "weight": 10,
                "context": {"lift_families": ["squat"]},
                "reason": "Coach chose to prefer the explicitly tagged right-loaded option.",
            }, f"coach_technical_observation:{observation.id}"),
        ])
        db.session.commit()

        ranked = AccessoryIntelligence().candidates(
            phase="development", lift_families={"squat"}, athlete_id=athlete.id,
            as_of=date(2026, 8, 12),
        )
        assert [item.exercise.name for item in ranked] == [
            "Right-loaded split squat", "Left-loaded split squat"
        ]
        assert ranked[0].state_score == 10
        assert ranked[1].state_score == -20
        assert ranked[1].provenance[0]["source_refs"] == [
            f"coach_technical_observation:{observation.id}"
        ]
        assert "diagnos" not in " ".join(ranked[0].reasons).casefold()


def test_athlete_reported_elbow_irritation_can_explicitly_exclude_bench_candidate(app):
    with app.app_context():
        athlete = _athlete()
        loaded = _exercise("Elbow-loaded extension", "elbow_loaded")
        neutral = _exercise("Neutral row", "neutral_upper")
        flag = AthleteConstraintFlag(
            athlete=athlete,
            flag_kind="irritation",
            label="Elbow irritation",
            details="Athlete reported symptoms; no diagnosis recorded.",
            reported_by="athlete",
            starts_on=date(2026, 8, 11),
        )
        db.session.add_all([loaded, neutral, flag])
        db.session.flush()
        db.session.add(_signal(athlete.id, {
            "rule_id": "coach.elbow.exclude.v1",
            "effect": "exclude",
            "candidate_tags": ["elbow_loaded"],
            "context": {"lift_families": ["bench"]},
            "reason": "Coach explicitly excluded the tagged loading pattern while the report is active.",
        }, f"athlete_constraint_flag:{flag.id}"))
        db.session.commit()

        evaluation = AccessoryIntelligence().evaluate_candidates(
            phase="strength", lift_families={"bench"}, athlete_id=athlete.id,
            as_of=date(2026, 8, 12),
        )
        assert [item.exercise.name for item in evaluation.candidates] == ["Neutral row"]
        assert [item.exercise.name for item in evaluation.excluded] == ["Elbow-loaded extension"]
        assert evaluation.excluded[0].provenance[0]["effect"] == "exclude"
        assert evaluation.excluded[0].provenance[0]["source_refs"] == [
            f"athlete_constraint_flag:{flag.id}"
        ]

        # The stored session/lift context is authoritative.
        deadlift = AccessoryIntelligence().candidates(
            phase="strength", lift_families={"deadlift"}, athlete_id=athlete.id,
            as_of=date(2026, 8, 12),
        )
        assert [item.exercise.name for item in deadlift] == [
            "Elbow-loaded extension", "Neutral row"
        ]


def test_coach_override_distinguishes_low_back_penalty_from_hip_exclusion(app):
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            _exercise("Axial assistance", "low_back_loaded", priority=10),
            _exercise("Hip-loaded assistance", "left_hip_loaded", priority=9),
            _exercise("Supported assistance", "externally_supported", priority=1),
            AthleteStateOverride(
                athlete=athlete,
                target_type="assistance_selection_rule",
                target_ref="coach.low-back.penalty.v1",
                override_json={
                    "effect": "penalty",
                    "candidate_tags": ["low_back_loaded"],
                    "weight": 30,
                    "context": {"phases": ["development"], "session_tags": ["lower"]},
                },
                reason="Coach explicitly reduced priority for this tagged loading context.",
                recorded_by="coach@example.test",
            ),
            AthleteStateOverride(
                athlete=athlete,
                target_type="assistance_selection_rule",
                target_ref="coach.left-hip.exclude.v1",
                override_json={
                    "effect": "exclude",
                    "candidate_tags": ["left_hip_loaded"],
                    "context": {"session_tags": ["lower"]},
                },
                reason="Coach explicitly excluded this sided tag for the session.",
                recorded_by="coach@example.test",
            ),
        ])
        db.session.commit()

        evaluation = AccessoryIntelligence().evaluate_candidates(
            phase="development", lift_families={"squat"}, session_tags={"lower"},
            athlete_id=athlete.id, as_of=date(2026, 8, 12),
        )
        assert [item.exercise.name for item in evaluation.candidates] == [
            "Supported assistance", "Axial assistance"
        ]
        assert evaluation.candidates[1].state_score == -30
        assert [item.exercise.name for item in evaluation.excluded] == [
            "Hip-loaded assistance"
        ]
        assert evaluation.candidates[1].provenance[0]["source"].startswith(
            "athlete_state_override:"
        )


def test_block_factory_consumes_state_ranking_and_keeps_provenance(app):
    with app.app_context():
        athlete = _athlete()
        higher = _exercise("Higher catalogue priority", "left_hip_loaded", priority=10)
        preferred = _exercise("State-preferred option", "right_hip_loaded", priority=1)
        higher.lift_relevance = preferred.lift_relevance = '["squat"]'
        db.session.add_all([
            higher,
            preferred,
            _signal(athlete.id, {
                "rule_id": "coach.session-sided-preference.v1",
                "effect": "preference",
                "candidate_tags": ["right_hip_loaded"],
                "weight": 20,
                "context": {"lift_families": ["squat"]},
                "reason": "Coach explicitly preferred the tagged option for squat sessions.",
            }, "coach_technical_observation:123"),
        ])
        db.session.commit()

        request = FactoryRequest(
            athlete_id=athlete.id,
            name="State bridge",
            week_count=1,
            training_days=3,
            split="POWERLIFTING_4",
            goal="development",
            squat_frequency=1,
            bench_frequency=1,
            deadlift_frequency=1,
            deadlift_style="conventional",
            meet_date=None,
            accessory_volume="low",
        )
        accessories = [item for day in _preview(request) for item in day["accessories"]]

        assert accessories[0]["name"] == "State-preferred option"
        assert accessories[0]["state_score"] == 20
        assert accessories[0]["state_provenance"][0]["rule_id"] == (
            "coach.session-sided-preference.v1"
        )
