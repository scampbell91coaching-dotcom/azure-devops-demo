import pytest

from portal.services.plan_entitlements import (
    DecisionReason,
    EntitlementAction,
    EntitlementDecision,
    EntitlementDenied,
    EntitlementRequest,
    LegacyAllowAllEntitlementProvider,
    PlanEntitlementService,
    PlanFeature,
)


class Decisions:
    def __init__(self, decision):
        self.decision = decision

    def decide(self, request):
        return self.decision


def request(**changes):
    values = {
        "tenant_id": "org-7",
        "feature": PlanFeature.ATHLETE_SEATS,
        "action": EntitlementAction.RESERVE,
    }
    values.update(changes)
    return EntitlementRequest(**values)


def test_request_requires_explicit_tenant_and_positive_amount():
    with pytest.raises(ValueError, match="tenant_id"):
        request(tenant_id="  ")
    with pytest.raises(ValueError, match="amount"):
        request(amount=0)


def test_require_returns_allowed_decision_with_limit_context():
    item = request(amount=2)
    decision = EntitlementDecision(
        request=item,
        allowed=True,
        reason=DecisionReason.ENTITLED,
        limit=10,
        used=7,
    )
    result = PlanEntitlementService(Decisions(decision)).require(item)
    assert result is decision
    assert result.remaining == 3


def test_require_raises_stable_domain_error_for_limit_denial():
    item = request()
    decision = EntitlementDecision(
        request=item,
        allowed=False,
        reason=DecisionReason.LIMIT_EXCEEDED,
        limit=10,
        used=10,
    )
    with pytest.raises(EntitlementDenied) as raised:
        PlanEntitlementService(Decisions(decision)).require(item)
    assert raised.value.decision is decision


def test_provider_cannot_return_a_decision_for_another_tenant():
    wanted = request(tenant_id="org-a")
    leaked = EntitlementDecision(
        request=request(tenant_id="org-b"),
        allowed=True,
        reason=DecisionReason.ENTITLED,
    )
    with pytest.raises(RuntimeError, match="mismatched request"):
        PlanEntitlementService(Decisions(leaked)).check(wanted)


def test_decision_rejects_inconsistent_allow_reason():
    with pytest.raises(ValueError, match="entitled reason"):
        EntitlementDecision(
            request=request(),
            allowed=True,
            reason=DecisionReason.FEATURE_DISABLED,
        )


def test_legacy_adapter_is_explicit_and_preserves_existing_behavior():
    item = request(
        feature=PlanFeature.PROGRAMMING,
        action=EntitlementAction.UPDATE,
    )
    decision = PlanEntitlementService(
        LegacyAllowAllEntitlementProvider()
    ).require(item)
    assert decision.allowed is True
    assert decision.reason is DecisionReason.ENTITLED
