"""Fail-closed policy primitives for future SaaS support adapters.

This module deliberately has no Flask/session integration.  A future adapter must
authenticate a support principal, load its explicit capabilities, and persist an
audit event before performing an authorised action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class SupportCapability(StrEnum):
    VIEW_SENSITIVE = "support:view_sensitive"
    DELEGATE_SESSION = "support:delegate_session"
    CHANGE_ACCOUNT_STATE = "support:change_account_state"


class SupportAction(StrEnum):
    VIEW_SENSITIVE = "view_sensitive"
    START_DELEGATION = "start_delegation"
    END_DELEGATION = "end_delegation"
    SUSPEND_ACCOUNT = "suspend_account"
    REACTIVATE_ACCOUNT = "reactivate_account"


class AuditVisibility(StrEnum):
    TENANT = "tenant"
    INTERNAL = "internal"


_REQUIRED_CAPABILITY = {
    SupportAction.VIEW_SENSITIVE: SupportCapability.VIEW_SENSITIVE,
    SupportAction.START_DELEGATION: SupportCapability.DELEGATE_SESSION,
    SupportAction.END_DELEGATION: SupportCapability.DELEGATE_SESSION,
    SupportAction.SUSPEND_ACCOUNT: SupportCapability.CHANGE_ACCOUNT_STATE,
    SupportAction.REACTIVATE_ACCOUNT: SupportCapability.CHANGE_ACCOUNT_STATE,
}


class SupportAuthorizationError(PermissionError):
    """Raised when a support action is not explicitly authorised."""


@dataclass(frozen=True)
class SupportPrincipal:
    subject: str
    capabilities: frozenset[SupportCapability] = frozenset()
    active: bool = False
    delegated: bool = False


@dataclass(frozen=True)
class SupportActionRequest:
    action: SupportAction
    tenant_ref: str
    reason: str
    reference: str
    target_account_ref: str | None = None
    delegation_expires_at: datetime | None = None
    tenant_visible: bool = True


@dataclass(frozen=True)
class AuthorizedSupportAction:
    actor_subject: str
    request: SupportActionRequest
    capability: SupportCapability
    visibility: AuditVisibility
    authorized_at: datetime


def authorize_support_action(
    principal: SupportPrincipal,
    request: SupportActionRequest,
    *,
    now: datetime | None = None,
    maximum_delegation: timedelta = timedelta(hours=1),
) -> AuthorizedSupportAction:
    """Authorize an action; absence of any required evidence denies it.

    Tenant membership/identity resolution remains an adapter responsibility.
    The opaque ``tenant_ref`` must come from that trusted resolution, never from
    an unverified request parameter.
    """

    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not principal.active or not principal.subject.strip():
        raise SupportAuthorizationError("an active support principal is required")
    if principal.delegated:
        raise SupportAuthorizationError("delegated sessions cannot initiate support actions")
    required = _REQUIRED_CAPABILITY[request.action]
    if required not in principal.capabilities:
        raise SupportAuthorizationError("the explicit support capability is required")
    if not request.tenant_ref.strip():
        raise SupportAuthorizationError("a resolved tenant is required")
    if not request.reason.strip() or not request.reference.strip():
        raise SupportAuthorizationError("a reason and ticket/reference are required")

    if request.action == SupportAction.START_DELEGATION:
        expiry = request.delegation_expires_at
        if expiry is None or expiry.tzinfo is None:
            raise SupportAuthorizationError("delegation requires a timezone-aware expiry")
        if expiry <= instant or expiry > instant + maximum_delegation:
            raise SupportAuthorizationError("delegation expiry is outside the allowed window")
    elif request.delegation_expires_at is not None:
        raise SupportAuthorizationError("expiry is only valid when starting delegation")

    if request.action in {
        SupportAction.SUSPEND_ACCOUNT,
        SupportAction.REACTIVATE_ACCOUNT,
    } and not (request.target_account_ref or "").strip():
        raise SupportAuthorizationError("account-state actions require a target account")

    visibility = (
        AuditVisibility.TENANT if request.tenant_visible else AuditVisibility.INTERNAL
    )
    return AuthorizedSupportAction(
        actor_subject=principal.subject,
        request=request,
        capability=required,
        visibility=visibility,
        authorized_at=instant,
    )
