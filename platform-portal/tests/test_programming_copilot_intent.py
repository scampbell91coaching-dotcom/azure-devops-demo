from dataclasses import FrozenInstanceError

import pytest

from portal.services.programming_copilot_intent import (
    BlockType,
    BodySide,
    ChangeKind,
    DeterministicProgrammingIntentParser,
    ProgrammingIntentParser,
)


def test_goal_example_parses_to_reviewable_contract():
    text = (
        "Use old sheet Jack 1. Left side low back pain. 8 week strength block. "
        "Build to RPE 8.5 week 7. Keep bench frequency."
    )

    intent = DeterministicProgrammingIntentParser().parse(text)

    assert intent.reference_programme.value == "Jack 1"
    assert intent.block_type.value is BlockType.STRENGTH
    assert intent.duration_weeks.value == 8
    assert (intent.target_rpe.rpe, intent.target_rpe.week) == (8.5, 7)
    assert [(item.subject) for item in intent.preserve] == ["bench frequency"]
    assert len(intent.athlete_observations) == 1
    observation = intent.athlete_observations[0]
    assert (observation.side, observation.location, observation.observation) == (
        BodySide.LEFT,
        "low back",
        "pain",
    )
    assert intent.unresolved == ()
    assert intent.review_required is False
    assert all(
        value.provenance.source == "coach_text"
        for value in (intent.reference_programme, intent.block_type, intent.duration_weeks)
    )


def test_supported_directives_and_authoring_intents_are_explicit():
    text = (
        "4-week hypertrophy block; increase squat frequency to 3; "
        "decrease deadlift volume; change split to upper lower; "
        "warm-up: extra hip mobility; assistance: hamstring and upper back focus; "
        "override training days: 4"
    )

    intent = DeterministicProgrammingIntentParser().parse(text)

    assert [(item.kind, item.subject, item.target) for item in intent.changes] == [
        (ChangeKind.INCREASE, "squat frequency", "3"),
        (ChangeKind.DECREASE, "deadlift volume", None),
        (ChangeKind.CHANGE, "split", "upper lower"),
    ]
    assert intent.warm_up_intent.value == "extra hip mobility"
    assert intent.assistance_intent.value == "hamstring and upper back focus"
    assert [(item.subject, item.value) for item in intent.coach_overrides] == [
        ("training days", "4")
    ]
    assert intent.unresolved == ()


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Make it spicy", "unsupported or ambiguous shorthand"),
        (
            "4 week strength block. Build to RPE 8 week 6",
            "target week is outside the requested block duration",
        ),
        (
            "4 week strength block. Build to RPE 11 week 4",
            "RPE must be between 1 and 10",
        ),
        (
            "4 week strength block. 6 week peaking block",
            "multiple block directives require coach review",
        ),
    ],
)
def test_invalid_or_ambiguous_intent_requires_coach_review(text, reason):
    intent = DeterministicProgrammingIntentParser().parse(text)

    assert intent.review_required is True
    assert reason in {item.reason for item in intent.unresolved}


def test_empty_intent_requires_review():
    intent = DeterministicProgrammingIntentParser().parse("   ")

    assert intent.review_required is True
    assert intent.unresolved[0].reason == "intent is empty"


def test_contract_is_immutable_and_parser_matches_adapter_protocol():
    parser = DeterministicProgrammingIntentParser()
    assert isinstance(parser, ProgrammingIntentParser)
    intent = parser.parse("8 week strength block")

    with pytest.raises(FrozenInstanceError):
        intent.source_text = "changed"


def test_provenance_span_round_trips_to_original_text():
    text = "Keep bench frequency. Left shoulder discomfort."
    intent = DeterministicProgrammingIntentParser().parse(text)

    sources = [intent.preserve[0].provenance, intent.athlete_observations[0].provenance]
    assert [text[item.start:item.end] for item in sources] == [item.text for item in sources]
    assert all(item.confidence == 1.0 for item in sources)
