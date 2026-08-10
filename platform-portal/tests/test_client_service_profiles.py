from datetime import UTC, date, datetime

import pytest

from portal.services.client_service_profiles import (
    ClientServiceProfile,
    ClientServiceProfileService,
    CoachServiceOverride,
    EntitlementProvenance,
    Service,
    VideoReviewEntitlement,
)


class Profiles:
    def __init__(self, *profiles):
        self.profiles = profiles

    def for_athlete(self, athlete_id):
        return [item for item in self.profiles if item.athlete_id == athlete_id]


def profile(**changes):
    values = {
        "athlete_id": 7,
        "training_coaching_enabled": True,
        "nutrition_coaching_enabled": True,
        "meet_day_support_enabled": True,
        "video_review_entitlement": VideoReviewEntitlement.NONE,
        "effective_from": date(2026, 1, 1),
        "provenance": EntitlementProvenance.COACH_CREATED,
    }
    values.update(changes)
    return ClientServiceProfile(**values)


@pytest.mark.parametrize(
    ("training", "nutrition"),
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_training_and_nutrition_are_independent(training, nutrition):
    item = profile(
        training_coaching_enabled=training,
        nutrition_coaching_enabled=nutrition,
    )
    assert item.enables(Service.TRAINING_COACHING) is training
    assert item.enables(Service.NUTRITION_COACHING) is nutrition


def test_missing_persisted_profile_uses_legacy_compatibility_defaults():
    result = ClientServiceProfileService(Profiles()).effective_profile(
        7, as_of=date(2026, 8, 10)
    )
    assert result.provenance is EntitlementProvenance.LEGACY_DEFAULT
    assert result.training_coaching_enabled is True
    assert result.nutrition_coaching_enabled is True
    assert result.meet_day_support_enabled is False
    assert result.video_review_entitlement is VideoReviewEntitlement.NONE


def test_periods_are_start_inclusive_and_end_exclusive():
    old = profile(effective_until=date(2026, 8, 10))
    current = profile(
        training_coaching_enabled=False,
        effective_from=date(2026, 8, 10),
    )
    service = ClientServiceProfileService(Profiles(old, current))
    assert service.effective_profile(7, as_of=date(2026, 8, 9)) == old
    assert service.effective_profile(
        7, as_of=date(2026, 8, 10)
    ).training_coaching_enabled is False


def test_dated_coach_override_is_partial_and_auditable():
    item = profile(
        video_review_entitlement=VideoReviewEntitlement.LIMITED,
        coach_override=CoachServiceOverride(
            actor="coach-12",
            reason="Meet preparation package",
            effective_from=date(2026, 8, 1),
            effective_until=date(2026, 8, 15),
            meet_day_support_enabled=False,
            video_review_entitlement=VideoReviewEntitlement.INCLUDED,
        ),
    )
    before = item.effective(date(2026, 7, 31))
    during = item.effective(date(2026, 8, 10))
    after = item.effective(date(2026, 8, 15))
    assert before is item and after is item
    assert during.meet_day_support_enabled is False
    assert during.video_review_entitlement is VideoReviewEntitlement.INCLUDED
    assert during.training_coaching_enabled is True
    assert during.provenance is EntitlementProvenance.COACH_OVERRIDE


def test_later_recorded_profile_wins_same_day_without_overwriting_history():
    # Adapters may return naive database timestamps or timezone-aware values.
    first = profile(recorded_at=datetime(2026, 8, 1))
    correction = profile(
        training_coaching_enabled=False,
        recorded_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    result = ClientServiceProfileService(Profiles(first, correction)).effective_profile(
        7, as_of=date(2026, 8, 10)
    )
    assert result is correction
    assert first.training_coaching_enabled is True


def test_disabling_service_only_gates_new_activity_not_historical_reads():
    disabled = profile(
        training_coaching_enabled=False,
        nutrition_coaching_enabled=False,
        meet_day_support_enabled=False,
    )
    service = ClientServiceProfileService(Profiles(disabled))
    assert (
        service.may_start_service(
            7, Service.TRAINING_COACHING, as_of=date(2026, 8, 10)
        )
        is False
    )
    # Historical models are intentionally absent from this API: callers keep
    # reading stored check-ins, programmes and meet records after disablement.


def test_override_requires_a_real_change_and_audit_details():
    with pytest.raises(ValueError, match="actor and reason"):
        CoachServiceOverride(
            actor="",
            reason="",
            effective_from=date(2026, 8, 1),
            training_coaching_enabled=False,
        )
    with pytest.raises(ValueError, match="at least one"):
        CoachServiceOverride(
            actor="coach",
            reason="correction",
            effective_from=date(2026, 8, 1),
        )
