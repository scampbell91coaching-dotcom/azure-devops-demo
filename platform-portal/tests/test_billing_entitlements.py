import pytest

from portal.billing.entitlements import (
    EntitlementService,
    LimitKind,
    Plan,
    SubscriptionSnapshot,
    SubscriptionState,
)


def subscription(state=SubscriptionState.ACTIVE, plan="starter"):
    return SubscriptionSnapshot("org-a", plan, state)


@pytest.mark.parametrize(
    "state,allowed",
    [
        (SubscriptionState.TRIALING, True),
        (SubscriptionState.ACTIVE, True),
        (SubscriptionState.PAST_DUE, True),
        (SubscriptionState.CANCELLED, False),
        (SubscriptionState.INCOMPLETE, False),
    ],
)
def test_subscription_state_controls_capability_access(state, allowed):
    decision = EntitlementService().capability(subscription(state), "programming")
    assert decision.allowed is allowed


def test_unknown_plan_and_capability_fail_closed():
    service = EntitlementService()
    assert service.capability(subscription(plan="invented"), "programming").reason == "unknown_plan"
    assert service.capability(subscription(), "nutrition").reason == "capability_not_in_plan"


def test_athlete_and_coach_capacity_are_independent_and_enforce_boundary():
    service = EntitlementService()
    assert service.capacity(subscription(), LimitKind.ATHLETES, 9).allowed
    assert service.capacity(subscription(), LimitKind.ATHLETES, 10).reason == "athletes_limit_reached"
    assert service.capacity(subscription(), LimitKind.COACHES, 1).reason == "coaches_limit_reached"


def test_unlimited_capacity_and_invalid_counts():
    service = EntitlementService()
    assert service.capacity(subscription(plan="unlimited"), LimitKind.ATHLETES, 1_000_000).allowed
    with pytest.raises(ValueError, match="cannot be negative"):
        service.capacity(subscription(), LimitKind.ATHLETES, -1)


def test_plan_contract_rejects_invalid_limits():
    with pytest.raises(ValueError, match="athlete limit"):
        Plan("bad", -1, 1, frozenset())
