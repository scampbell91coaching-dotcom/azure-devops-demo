from __future__ import annotations

from datetime import UTC, date, datetime

from ..models.client_service import ClientServiceChange
from .client_service_profiles import (
    ClientServiceProfile,
    ClientServiceProfileRepository,
    ClientServiceProfileService,
    EntitlementProvenance,
    Service,
    VideoReviewEntitlement,
)

SERVICE_DEFINITIONS = (
    ("training", "Training coaching", ("yes", "no")),
    ("nutrition", "Nutrition coaching", ("yes", "no")),
    ("meet_day", "Meet-day support", ("yes", "no")),
    ("video_review", "Video review", ("none", "limited", "included")),
)

DEFAULTS = {
    "training": "yes",
    "nutrition": "no",
    "meet_day": "no",
    "video_review": "none",
}

_DOMAIN_TO_STORAGE = {
    Service.TRAINING_COACHING: "training",
    Service.NUTRITION_COACHING: "nutrition",
    Service.MEET_DAY_SUPPORT: "meet_day",
    Service.VIDEO_REVIEW: "video_review",
}


class SqlAlchemyClientServiceProfileRepository(ClientServiceProfileRepository):
    def for_athlete(self, athlete_id: int):
        changes = (
            ClientServiceChange.query.filter_by(athlete_id=athlete_id)
            .order_by(
                ClientServiceChange.effective_at.asc(),
                ClientServiceChange.created_at.asc(),
                ClientServiceChange.id.asc(),
            )
            .all()
        )

        if not changes:
            return ()

        state = {
            "training": "yes",
            "nutrition": "no",
            "meet_day": "no",
            "video_review": "none",
        }

        profiles = []

        for change in changes:
            state[change.service] = change.value

            profiles.append(
                ClientServiceProfile(
                    athlete_id=athlete_id,
                    training_coaching_enabled=state["training"] == "yes",
                    nutrition_coaching_enabled=state["nutrition"] == "yes",
                    meet_day_support_enabled=state["meet_day"] == "yes",
                    video_review_entitlement=VideoReviewEntitlement(
                        state["video_review"]
                    ),
                    effective_from=change.effective_at.date(),
                    recorded_at=change.created_at,
                    provenance=EntitlementProvenance.COACH_CREATED,
                )
            )

        return tuple(profiles)


def client_service_profile_service() -> ClientServiceProfileService:
    return ClientServiceProfileService(SqlAlchemyClientServiceProfileRepository())


def effective_client_service_profile(
    athlete_id: int,
    *,
    as_of: date | None = None,
    at: datetime | None = None,
) -> ClientServiceProfile:
    """Resolve persisted service decisions using full datetime precision."""

    if at is not None and as_of is not None:
        raise ValueError("provide either as_of or at, not both")

    if at is not None:
        cutoff = at
        if cutoff.tzinfo is not None:
            cutoff = cutoff.astimezone(UTC).replace(tzinfo=None)
    elif as_of is not None:
        cutoff = datetime.combine(as_of, datetime.max.time())
    else:
        cutoff = datetime.now(UTC).replace(tzinfo=None)

    changes = (
        ClientServiceChange.query.filter(
            ClientServiceChange.athlete_id == athlete_id,
            ClientServiceChange.effective_at <= cutoff,
        )
        .order_by(
            ClientServiceChange.effective_at.asc(),
            ClientServiceChange.created_at.asc(),
            ClientServiceChange.id.asc(),
        )
        .all()
    )

    if not changes:
        # No persisted decisions means legacy compatibility.
        return ClientServiceProfile.legacy_default(
            athlete_id,
            as_of=cutoff.date(),
        )

    state = {
        "training": "yes",
        "nutrition": "yes",
        "meet_day": "no",
        "video_review": "none",
    }

    latest_by_service: dict[str, ClientServiceChange] = {}

    for change in changes:
        state[change.service] = change.value
        latest_by_service[change.service] = change

    latest_changes = list(latest_by_service.values())

    return ClientServiceProfile(
        athlete_id=athlete_id,
        training_coaching_enabled=state["training"] == "yes",
        nutrition_coaching_enabled=state["nutrition"] == "yes",
        meet_day_support_enabled=state["meet_day"] == "yes",
        video_review_entitlement=VideoReviewEntitlement(
            state["video_review"]
        ),
        effective_from=min(
            change.effective_at for change in latest_changes
        ).date(),
        recorded_at=max(
            change.created_at for change in latest_changes
        ),
        provenance=EntitlementProvenance.COACH_CREATED,
    )


def may_start_client_service(
    athlete_id: int,
    service: Service,
    *,
    as_of: date | None = None,
    at: datetime | None = None,
) -> bool:
    return effective_client_service_profile(
        athlete_id,
        as_of=as_of,
        at=at,
    ).enables(service)


def nutrition_enabled_athlete_ids(athlete_ids: list[int] | tuple[int, ...]) -> set[int]:
    """Resolve current nutrition entitlement for many athletes with one query."""
    ids = [int(athlete_id) for athlete_id in athlete_ids]
    if not ids:
        return set()

    changes = (
        ClientServiceChange.query.filter(
            ClientServiceChange.athlete_id.in_(ids),
            ClientServiceChange.service == "nutrition",
            ClientServiceChange.effective_at <= datetime.now(UTC).replace(tzinfo=None),
        )
        .order_by(
            ClientServiceChange.athlete_id.asc(),
            ClientServiceChange.effective_at.asc(),
            ClientServiceChange.created_at.asc(),
            ClientServiceChange.id.asc(),
        )
        .all()
    )

    latest: dict[int, ClientServiceChange] = {}
    for change in changes:
        latest[change.athlete_id] = change

    enabled = set()

    for athlete_id in ids:
        current = latest.get(athlete_id)

        # No persisted entitlement history means legacy compatibility.
        if current is None or current.value == "yes":
            enabled.add(athlete_id)

    return enabled

def resolved_client_services(athlete_id: int, *, now: datetime | None = None):
    """Return effective UI state plus the next scheduled decision for each service."""
    at = (now or datetime.now(UTC)).replace(tzinfo=None)

    changes = (
        ClientServiceChange.query.filter_by(athlete_id=athlete_id)
        .order_by(
            ClientServiceChange.effective_at.asc(),
            ClientServiceChange.created_at.asc(),
            ClientServiceChange.id.asc(),
        )
        .all()
    )

    profile = effective_client_service_profile(
        athlete_id,
        at=at,
    )

    domain_values = {
        "training": "yes" if profile.training_coaching_enabled else "no",
        "nutrition": "yes" if profile.nutrition_coaching_enabled else "no",
        "meet_day": "yes" if profile.meet_day_support_enabled else "no",
        "video_review": profile.video_review_entitlement.value,
    }

    result = []

    for key, label, choices in SERVICE_DEFINITIONS:
        service_changes = [change for change in changes if change.service == key]
        effective = [change for change in service_changes if change.effective_at <= at]
        scheduled = next(
            (change for change in service_changes if change.effective_at > at),
            None,
        )

        current = effective[-1] if effective else None

        result.append(
            {
                "key": key,
                "label": label,
                "choices": choices,
                "value": domain_values[key],
                "provenance": (
                    current.changed_by.email
                    if current and current.changed_by
                    else profile.provenance.value
                ),
                "effective_at": current.effective_at if current else None,
                "scheduled": scheduled,
            }
        )

    return result
