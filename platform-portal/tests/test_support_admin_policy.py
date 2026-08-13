from datetime import UTC, datetime, timedelta

import pytest

from portal.services.support_admin import (
    AuditVisibility,
    SupportAction,
    SupportActionRequest,
    SupportAuthorizationError,
    SupportCapability,
    SupportPrincipal,
    authorize_support_action,
)

NOW = datetime(2026, 8, 12, 10, tzinfo=UTC)


def request(action=SupportAction.VIEW_SENSITIVE, **changes):
    values = dict(action=action, tenant_ref="coach:41", reason="Investigate failed sync", reference="SUP-123")
    values.update(changes)
    return SupportActionRequest(**values)


def principal(*capabilities, **changes):
    values = dict(subject="support@example.test", active=True, capabilities=frozenset(capabilities))
    values.update(changes)
    return SupportPrincipal(**values)


def test_ordinary_coach_or_user_has_no_support_access_by_default():
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(principal(), request(), now=NOW)


def test_inactive_support_principal_is_denied_even_with_capability():
    actor = principal(SupportCapability.VIEW_SENSITIVE, active=False)
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(actor, request(), now=NOW)


def test_matching_explicit_capability_authorizes_and_builds_tenant_audit_contract():
    result = authorize_support_action(
        principal(SupportCapability.VIEW_SENSITIVE), request(), now=NOW
    )
    assert result.capability == SupportCapability.VIEW_SENSITIVE
    assert result.visibility == AuditVisibility.TENANT
    assert result.request.reference == "SUP-123"


@pytest.mark.parametrize("field", ["reason", "reference"])
def test_sensitive_action_requires_reason_and_reference(field):
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(
            principal(SupportCapability.VIEW_SENSITIVE), request(**{field: " "}), now=NOW
        )


def test_delegated_session_cannot_create_another_support_action():
    actor = principal(SupportCapability.VIEW_SENSITIVE, delegated=True)
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(actor, request(), now=NOW)


def test_delegation_is_explicitly_capable_and_time_bounded():
    actor = principal(SupportCapability.DELEGATE_SESSION)
    allowed = request(
        SupportAction.START_DELEGATION,
        target_account_ref="user:8",
        delegation_expires_at=NOW + timedelta(minutes=30),
    )
    assert authorize_support_action(actor, allowed, now=NOW).request == allowed
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(
            actor,
            request(SupportAction.START_DELEGATION, delegation_expires_at=NOW + timedelta(hours=2)),
            now=NOW,
        )


@pytest.mark.parametrize("action", [SupportAction.SUSPEND_ACCOUNT, SupportAction.REACTIVATE_ACCOUNT])
def test_account_state_actions_require_specific_capability_and_target(action):
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(principal(SupportCapability.VIEW_SENSITIVE), request(action), now=NOW)
    with pytest.raises(SupportAuthorizationError):
        authorize_support_action(principal(SupportCapability.CHANGE_ACCOUNT_STATE), request(action), now=NOW)
    authorized = authorize_support_action(
        principal(SupportCapability.CHANGE_ACCOUNT_STATE),
        request(action, target_account_ref="account:9"),
        now=NOW,
    )
    assert authorized.request.target_account_ref == "account:9"
