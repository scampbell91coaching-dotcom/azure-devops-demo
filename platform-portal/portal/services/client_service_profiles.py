"""Schema-independent client service entitlement policy.

This module is the platform-owned domain seam.  It deliberately has no Flask,
SQLAlchemy, or billing dependency so persistence and route enforcement can be
added independently.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Protocol, Sequence


class VideoReviewEntitlement(StrEnum):
    NONE = "none"
    LIMITED = "limited"
    INCLUDED = "included"


class EntitlementProvenance(StrEnum):
    LEGACY_DEFAULT = "legacy_default"
    COACH_CREATED = "coach_created"
    COACH_OVERRIDE = "coach_override"
    ADMIN_CREATED = "admin_created"
    BILLING_SYNC = "billing_sync"


class Service(StrEnum):
    TRAINING_COACHING = "training_coaching"
    NUTRITION_COACHING = "nutrition_coaching"
    MEET_DAY_SUPPORT = "meet_day_support"
    VIDEO_REVIEW = "video_review"


@dataclass(frozen=True)
class CoachServiceOverride:
    """A dated, auditable partial replacement of a profile's values."""

    actor: str
    reason: str
    effective_from: date
    effective_until: date | None = None
    training_coaching_enabled: bool | None = None
    nutrition_coaching_enabled: bool | None = None
    meet_day_support_enabled: bool | None = None
    video_review_entitlement: VideoReviewEntitlement | None = None
    provenance: EntitlementProvenance = EntitlementProvenance.COACH_OVERRIDE

    def __post_init__(self) -> None:
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("coach override requires an actor and reason")
        _validate_period(self.effective_from, self.effective_until)
        if all(
            value is None
            for value in (
                self.training_coaching_enabled,
                self.nutrition_coaching_enabled,
                self.meet_day_support_enabled,
                self.video_review_entitlement,
            )
        ):
            raise ValueError("coach override must change at least one entitlement")
        if self.provenance is not EntitlementProvenance.COACH_OVERRIDE:
            raise ValueError("coach override provenance must be coach_override")

    def is_effective_on(self, as_of: date) -> bool:
        return _contains(self.effective_from, self.effective_until, as_of)


@dataclass(frozen=True)
class ClientServiceProfile:
    athlete_id: int
    training_coaching_enabled: bool
    nutrition_coaching_enabled: bool
    meet_day_support_enabled: bool
    video_review_entitlement: VideoReviewEntitlement
    effective_from: date
    provenance: EntitlementProvenance
    effective_until: date | None = None
    recorded_at: datetime | None = None
    coach_override: CoachServiceOverride | None = None

    def __post_init__(self) -> None:
        if self.athlete_id < 1:
            raise ValueError("athlete_id must be positive")
        _validate_period(self.effective_from, self.effective_until)

    @classmethod
    def legacy_default(cls, athlete_id: int, *, as_of: date) -> ClientServiceProfile:
        """Return safe defaults when no persisted entitlement history exists."""
        return cls(
            athlete_id=athlete_id,
            training_coaching_enabled=True,
            nutrition_coaching_enabled=False,
            meet_day_support_enabled=False,
            video_review_entitlement=VideoReviewEntitlement.NONE,
            effective_from=as_of,
            provenance=EntitlementProvenance.LEGACY_DEFAULT,
        )

    def is_effective_on(self, as_of: date) -> bool:
        return _contains(self.effective_from, self.effective_until, as_of)

    def effective(self, as_of: date) -> ClientServiceProfile:
        """Apply a coach override only inside its half-open effective period."""
        override = self.coach_override
        if override is None or not override.is_effective_on(as_of):
            return self
        return replace(
            self,
            training_coaching_enabled=_coalesce(
                override.training_coaching_enabled, self.training_coaching_enabled
            ),
            nutrition_coaching_enabled=_coalesce(
                override.nutrition_coaching_enabled, self.nutrition_coaching_enabled
            ),
            meet_day_support_enabled=_coalesce(
                override.meet_day_support_enabled, self.meet_day_support_enabled
            ),
            video_review_entitlement=(
                override.video_review_entitlement or self.video_review_entitlement
            ),
            provenance=override.provenance,
            coach_override=None,
        )

    def enables(self, service: Service) -> bool:
        if service is Service.TRAINING_COACHING:
            return self.training_coaching_enabled
        if service is Service.NUTRITION_COACHING:
            return self.nutrition_coaching_enabled
        if service is Service.MEET_DAY_SUPPORT:
            return self.meet_day_support_enabled
        return self.video_review_entitlement is not VideoReviewEntitlement.NONE


class ClientServiceProfileRepository(Protocol):
    def for_athlete(self, athlete_id: int) -> Sequence[ClientServiceProfile]: ...


class ClientServiceProfileService:
    def __init__(self, repository: ClientServiceProfileRepository):
        self.repository = repository

    def effective_profile(
        self, athlete_id: int, *, as_of: date | None = None
    ) -> ClientServiceProfile:
        on_date = as_of or datetime.now(UTC).date()
        candidates = [
            profile
            for profile in self.repository.for_athlete(athlete_id)
            if profile.is_effective_on(on_date)
        ]
        if not candidates:
            return ClientServiceProfile.legacy_default(athlete_id, as_of=on_date)
        # Later effective rows supersede older rows. recorded_at breaks ties and
        # supports corrections without mutating historical profile records.
        selected = max(
            candidates,
            key=lambda profile: (
                profile.effective_from,
                _recorded_sort_value(profile.recorded_at),
            ),
        )
        return selected.effective(on_date)

    def may_start_service(
        self, athlete_id: int, service: Service, *, as_of: date | None = None
    ) -> bool:
        """Gate new/current service activity, never reads of historical records."""
        return self.effective_profile(athlete_id, as_of=as_of).enables(service)


def _contains(starts_on: date, ends_before: date | None, as_of: date) -> bool:
    return starts_on <= as_of and (ends_before is None or as_of < ends_before)


def _validate_period(starts_on: date, ends_before: date | None) -> None:
    if ends_before is not None and ends_before <= starts_on:
        raise ValueError("effective_until must be after effective_from")


def _coalesce(value: bool | None, fallback: bool) -> bool:
    return fallback if value is None else value


def _recorded_sort_value(value: datetime | None) -> datetime:
    """Normalize SQLAlchemy-naive and timezone-aware values for ordering."""
    if value is None:
        return datetime.min
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
