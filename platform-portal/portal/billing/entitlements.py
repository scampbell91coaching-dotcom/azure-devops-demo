"""Pure entitlement policy; it deliberately has no payment-provider dependency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class SubscriptionState(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class LimitKind(StrEnum):
    ATHLETES = "athletes"
    COACHES = "coaches"


@dataclass(frozen=True)
class Plan:
    identifier: str
    athlete_limit: int | None
    coach_limit: int | None
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("plan identifier is required")
        if self.athlete_limit is not None and self.athlete_limit < 0:
            raise ValueError("athlete limit cannot be negative")
        if self.coach_limit is not None and self.coach_limit < 0:
            raise ValueError("coach limit cannot be negative")


@dataclass(frozen=True)
class SubscriptionSnapshot:
    organisation_id: str
    plan_identifier: str
    state: SubscriptionState


@dataclass(frozen=True)
class EntitlementDecision:
    allowed: bool
    reason: str


DEFAULT_PLANS: Mapping[str, Plan] = MappingProxyType(
    {
        "starter": Plan(
            identifier="starter",
            athlete_limit=10,
            coach_limit=1,
            capabilities=frozenset({"programming", "check_ins"}),
        ),
        "team": Plan(
            identifier="team",
            athlete_limit=100,
            coach_limit=5,
            capabilities=frozenset(
                {"programming", "check_ins", "nutrition", "reporting"}
            ),
        ),
        "unlimited": Plan(
            identifier="unlimited",
            athlete_limit=None,
            coach_limit=None,
            capabilities=frozenset(
                {"programming", "check_ins", "nutrition", "reporting"}
            ),
        ),
    }
)


class EntitlementService:
    """Makes fail-closed feature and capacity decisions for one organisation."""

    _ACCESS_STATES = frozenset(
        {SubscriptionState.TRIALING, SubscriptionState.ACTIVE, SubscriptionState.PAST_DUE}
    )

    def __init__(self, plans: Mapping[str, Plan] = DEFAULT_PLANS) -> None:
        self._plans = MappingProxyType(dict(plans))

    def capability(
        self, subscription: SubscriptionSnapshot, capability: str
    ) -> EntitlementDecision:
        plan, denial = self._eligible_plan(subscription)
        if denial:
            return denial
        if capability not in plan.capabilities:
            return EntitlementDecision(False, "capability_not_in_plan")
        return EntitlementDecision(True, "entitled")

    def capacity(
        self,
        subscription: SubscriptionSnapshot,
        kind: LimitKind,
        current_count: int,
    ) -> EntitlementDecision:
        if current_count < 0:
            raise ValueError("current count cannot be negative")
        plan, denial = self._eligible_plan(subscription)
        if denial:
            return denial
        limit = plan.athlete_limit if kind is LimitKind.ATHLETES else plan.coach_limit
        if limit is not None and current_count >= limit:
            return EntitlementDecision(False, f"{kind.value}_limit_reached")
        return EntitlementDecision(True, "capacity_available")

    def _eligible_plan(
        self, subscription: SubscriptionSnapshot
    ) -> tuple[Plan | None, EntitlementDecision | None]:
        if subscription.state not in self._ACCESS_STATES:
            return None, EntitlementDecision(False, "subscription_not_entitled")
        plan = self._plans.get(subscription.plan_identifier)
        if plan is None:
            return None, EntitlementDecision(False, "unknown_plan")
        return plan, None
