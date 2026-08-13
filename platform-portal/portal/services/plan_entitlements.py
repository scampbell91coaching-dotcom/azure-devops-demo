"""Schema-independent contracts for organization plan entitlement checks.

This is deliberately separate from ``client_service_profiles``.  A plan grants
an organization a product capability; a client-service profile records what a
coach has agreed to deliver to one athlete.  Effective access may require both,
but neither is a substitute for tenant authorization.

The module has no Flask, SQLAlchemy, or payment-provider dependency.  A future
adapter can therefore resolve persisted billing snapshots without making live
provider calls from request handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PlanFeature(StrEnum):
    ATHLETE_SEATS = "athlete_seats"
    COACH_MEMBER_SEATS = "coach_member_seats"
    PROGRAMMING = "programming"
    ANALYTICS = "analytics"
    NUTRITION = "nutrition"
    MEAL_PLAN_PDF_EXPORT = "meal_plan_pdf_export"
    COMPETITION_TOOLING = "competition_tooling"
    AI_COPILOT = "ai_copilot"
    STORAGE_BYTES = "storage_bytes"
    API_ACCESS = "api_access"


class EntitlementAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    EXPORT = "export"
    UPLOAD = "upload"
    RESERVE = "reserve"


class DecisionReason(StrEnum):
    ENTITLED = "entitled"
    FEATURE_DISABLED = "feature_disabled"
    LIMIT_EXCEEDED = "limit_exceeded"
    SUBSCRIPTION_INACTIVE = "subscription_inactive"


@dataclass(frozen=True, slots=True)
class EntitlementRequest:
    """A tenant-scoped capability request.

    ``amount`` is the number of units being requested.  Seat creation and
    uploads should use ``RESERVE`` and be evaluated atomically with the write by
    the persistence adapter.  ``resource_id`` is audit context only and must
    never replace tenant-qualified resource authorization.
    """

    tenant_id: str
    feature: PlanFeature
    action: EntitlementAction
    amount: int = 1
    actor_id: str | None = None
    resource_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if self.amount < 1:
            raise ValueError("amount must be positive")


@dataclass(frozen=True, slots=True)
class EntitlementDecision:
    request: EntitlementRequest
    allowed: bool
    reason: DecisionReason
    limit: int | None = None
    used: int | None = None

    def __post_init__(self) -> None:
        if self.allowed != (self.reason is DecisionReason.ENTITLED):
            raise ValueError("allowed decisions must use the entitled reason")
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit cannot be negative")
        if self.used is not None and self.used < 0:
            raise ValueError("used cannot be negative")

    @property
    def remaining(self) -> int | None:
        if self.limit is None or self.used is None:
            return None
        return max(self.limit - self.used, 0)


class EntitlementDecisionProvider(Protocol):
    """Port implemented by a tenant-qualified local persistence adapter."""

    def decide(self, request: EntitlementRequest) -> EntitlementDecision: ...


class EntitlementDenied(PermissionError):
    """Stable domain failure for HTTP, job, CLI, and service adapters."""

    def __init__(self, decision: EntitlementDecision):
        self.decision = decision
        super().__init__(
            f"{decision.request.feature.value} denied: {decision.reason.value}"
        )


class PlanEntitlementService:
    """Single application-facing entry point for organization plan checks."""

    def __init__(self, provider: EntitlementDecisionProvider):
        self._provider = provider

    def check(self, request: EntitlementRequest) -> EntitlementDecision:
        decision = self._provider.decide(request)
        if decision.request != request:
            # Prevent a broken cache or adapter from returning another tenant's
            # decision and accidentally granting cross-tenant access.
            raise RuntimeError("entitlement provider returned a mismatched request")
        return decision

    def require(self, request: EntitlementRequest) -> EntitlementDecision:
        decision = self.check(request)
        if not decision.allowed:
            raise EntitlementDenied(decision)
        return decision


class LegacyAllowAllEntitlementProvider:
    """Explicit compatibility adapter for a controlled single-tenant cutover.

    Do not use this as the default in a multi-tenant deployment.  It exists so
    legacy behavior can be selected deliberately while persisted organization
    subscriptions are backfilled and shadow-evaluated.
    """

    def decide(self, request: EntitlementRequest) -> EntitlementDecision:
        return EntitlementDecision(
            request=request,
            allowed=True,
            reason=DecisionReason.ENTITLED,
        )
