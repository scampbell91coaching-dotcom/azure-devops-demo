from datetime import date

import pytest

from portal.services.holiday_mode import (
    CoachOverride, HolidayPeriod, HolidayStatus, ProgrammingIntent, Provenance,
    SessionAction, SessionContext, TemporalState, TrainingAvailability,
    decide_session, overlapping_periods,
)


def holiday(**changes):
    values = dict(
        holiday_id="holiday-1", athlete_id=7,
        starts_on=date(2026, 8, 10), ends_on=date(2026, 8, 16),
        availability=TrainingAvailability.REDUCED,
        programming_intent=ProgrammingIntent.REDUCE,
        provenance=Provenance.ATHLETE_SUBMITTED,
        available_training_days=frozenset({0, 2}),
        equipment=frozenset({"dumbbells", "bench"}),
    )
    values.update(changes)
    return HolidayPeriod(**values)


def test_overlap_is_inclusive_deterministic_and_ignores_cancelled():
    periods = [
        holiday(holiday_id="b", starts_on=date(2026, 8, 16), ends_on=date(2026, 8, 20)),
        holiday(holiday_id="a"),
        holiday(holiday_id="cancelled", status=HolidayStatus.CANCELLED),
        holiday(holiday_id="other", athlete_id=8),
    ]
    assert overlapping_periods(periods) == (("a", "b"),)


def test_active_upcoming_and_completed_temporal_state():
    period = holiday()
    assert period.temporal_state(date(2026, 8, 9)) is TemporalState.UPCOMING
    assert period.temporal_state(date(2026, 8, 10)) is TemporalState.ACTIVE
    assert period.temporal_state(date(2026, 8, 17)) is TemporalState.PAST
    assert holiday(status=HolidayStatus.COMPLETED).temporal_state(date(2026, 8, 12)) is TemporalState.PAST


def test_equipment_limited_session_substitutes_and_preserves_original():
    decision = decide_session(
        holiday(programming_intent=ProgrammingIntent.SUBSTITUTE),
        SessionContext(date(2026, 8, 12), frozenset({"barbell", "rack"})),
    )
    assert decision.action is SessionAction.PROPOSE_SUBSTITUTE
    assert decision.preserve_original is True
    assert decision.reason == "missing equipment: barbell, rack"


def test_coach_override_wins_and_requires_audit_reason():
    with pytest.raises(ValueError, match="actor and reason"):
        CoachOverride(actor="coach:2", reason="")
    period = holiday(coach_override=CoachOverride(
        actor="coach:2", reason="Hotel gym confirmed",
        availability=TrainingAvailability.NORMAL,
        available_training_days=frozenset({1}), equipment=frozenset({"barbell"}),
        programming_intent=ProgrammingIntent.PRESERVE,
    ))
    allowed = decide_session(period, SessionContext(date(2026, 8, 11), frozenset({"barbell"})))
    unavailable = decide_session(period, SessionContext(date(2026, 8, 12), frozenset()))
    assert allowed.action is SessionAction.PRESENT_ORIGINAL_AWAY
    assert unavailable.action is SessionAction.OMIT_FROM_HOLIDAY_VIEW


def test_return_date_defaults_to_next_day_and_explicit_date_must_follow_trip():
    assert holiday().effective_return_date == date(2026, 8, 17)
    assert holiday(return_to_training_on=date(2026, 8, 19)).effective_return_date == date(2026, 8, 19)
    with pytest.raises(ValueError, match="after the holiday"):
        holiday(return_to_training_on=date(2026, 8, 16))


def test_no_training_has_deterministic_pause_policy():
    period = holiday(availability=TrainingAvailability.NONE,
                     programming_intent=ProgrammingIntent.PAUSE,
                     available_training_days=frozenset())
    assert decide_session(period, SessionContext(date(2026, 8, 12))).action is SessionAction.OMIT_FROM_HOLIDAY_VIEW
    with pytest.raises(ValueError, match="require pause"):
        holiday(availability=TrainingAvailability.NONE,
                available_training_days=frozenset())
