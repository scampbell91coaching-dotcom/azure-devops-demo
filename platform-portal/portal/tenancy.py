"""Fail-closed organisation context and authorization primitives.

Global :class:`UserRole` values describe the kind of platform identity that
authenticated.  They do not grant authority inside an Organisation.  That
authority comes only from the active ``OrganisationMembership`` resolved here.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from flask import abort, current_app, g, session
from sqlalchemy import false, select
from sqlalchemy.orm import Query

from .models.organisation import (
    CoachAthleteOwnership,
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
    OwnershipStatus,
)
from .models.user import User, UserRole


class TenancyResolutionError(RuntimeError):
    """Raised when a request cannot establish one authorised Organisation."""


class TenantObjectNotFound(LookupError):
    """Raised without disclosing whether an object exists in another tenant."""


@dataclass(frozen=True, slots=True)
class TenancyContext:
    user_id: int
    organisation_id: int
    membership_id: int
    role: OrganisationRole


def resolve_tenancy_context(
    user: User, *, organisation_id: int | None = None
) -> TenancyContext:
    """Resolve a current, active membership for an authenticated coach.

    A missing selection is accepted only when there is exactly one active
    membership.  This makes single-Organisation sessions convenient without
    allowing an arbitrary membership to win for multi-Organisation users.
    """
    if user.id is None or not user.active or user.user_role != UserRole.COACH:
        raise TenancyResolutionError("an active coach identity is required")
    if organisation_id is not None and (
        not isinstance(organisation_id, int) or isinstance(organisation_id, bool)
    ):
        raise TenancyResolutionError("a valid Organisation selection is required")

    query = (
        OrganisationMembership.query.join(Organisation)
        .filter(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.status == MembershipStatus.ACTIVE,
            Organisation.active.is_(True),
        )
    )
    if organisation_id is not None:
        membership = query.filter(
            OrganisationMembership.organisation_id == organisation_id
        ).one_or_none()
    else:
        matches = query.limit(2).all()
        membership = matches[0] if len(matches) == 1 else None

    if membership is None:
        raise TenancyResolutionError(
            "an active Organisation and membership selection is required"
        )
    return TenancyContext(
        user_id=user.id,
        organisation_id=membership.organisation_id,
        membership_id=membership.id,
        role=OrganisationRole(membership.role),
    )


def current_tenancy_context() -> TenancyContext:
    """Return the request context, resolving it once from trusted session state."""
    cached = g.get("tenancy_context")
    if isinstance(cached, TenancyContext):
        return cached
    user = g.get("current_user")
    if user is None:
        raise TenancyResolutionError("authentication is required")
    selected = session.get("organisation_id")
    context = resolve_tenancy_context(user, organisation_id=selected)
    g.tenancy_context = context
    return context


def require_tenancy_context() -> TenancyContext:
    """Resolve request tenancy or reject absent and ambiguous coach scope."""
    try:
        return current_tenancy_context()
    except TenancyResolutionError:
        abort(403)


ModelT = TypeVar("ModelT")


def tenant_scoped_query(context: TenancyContext, model: type[ModelT]) -> Query:
    """Start a query that can never silently fall back to global object scope."""
    organisation_column = getattr(model, "organisation_id", None)
    if organisation_column is None:
        raise TypeError(f"{model.__name__} is not directly Organisation-scoped")
    return model.query.filter(organisation_column == context.organisation_id)


def load_tenant_object(
    context: TenancyContext, model: type[ModelT], object_id: Any
) -> ModelT:
    """Load by Organisation and ID, concealing cross-tenant existence."""
    item = (
        tenant_scoped_query(context, model)
        .filter(model.id == object_id)
        .one_or_none()
    )
    if item is None:
        raise TenantObjectNotFound
    return item


def load_owned_athlete(context: TenancyContext, athlete_id: int):
    """Load an athlete actively owned by the current coach membership."""
    from .models.athlete import Athlete

    athlete = (
        Athlete.query.join(
            CoachAthleteOwnership,
            CoachAthleteOwnership.athlete_id == Athlete.id,
        )
        .filter(
            CoachAthleteOwnership.organisation_id == context.organisation_id,
            CoachAthleteOwnership.coach_membership_id == context.membership_id,
            CoachAthleteOwnership.status == OwnershipStatus.ACTIVE,
            Athlete.id == athlete_id,
        )
        .one_or_none()
    )
    if athlete is None:
        raise TenantObjectNotFound
    return athlete


def accessible_athlete_ids_query():
    """Return athlete IDs in the selected Organisation for the current coach."""
    if current_app.config["AUTHENTICATION_DISABLED"]:
        return select(CoachAthleteOwnership.athlete_id)
    try:
        context = current_tenancy_context()
    except TenancyResolutionError:
        return select(CoachAthleteOwnership.athlete_id).where(false())
    return select(CoachAthleteOwnership.athlete_id).where(
        CoachAthleteOwnership.organisation_id == context.organisation_id,
        CoachAthleteOwnership.coach_membership_id == context.membership_id,
        CoachAthleteOwnership.status == OwnershipStatus.ACTIVE,
    )


def athlete_query_for_request():
    """Scope athletes to self or the coach's selected Organisation."""
    from .models.athlete import Athlete

    if current_app.config["AUTHENTICATION_DISABLED"]:
        return Athlete.query
    user = g.get("current_user")
    if user is not None and user.user_role == UserRole.ATHLETE:
        return Athlete.query.filter(Athlete.id == user.athlete_id)
    return Athlete.query.filter(Athlete.id.in_(accessible_athlete_ids_query()))


def require_athlete_access(athlete_id: int):
    athlete = athlete_query_for_request().filter_by(id=athlete_id).one_or_none()
    if athlete is None:
        abort(404)
    return athlete


def require_single_coach_membership() -> OrganisationMembership | None:
    """Resolve the selected membership for ownership creation."""
    if current_app.config["AUTHENTICATION_DISABLED"]:
        return None
    context = require_tenancy_context()
    return OrganisationMembership.query.filter_by(id=context.membership_id).one()


def require_programming_access(item):
    """Conceal a block, week, or session outside the selected Organisation."""
    if item is None:
        abort(404)
    block = (
        item.week.block
        if hasattr(item, "week")
        else item.block
        if hasattr(item, "block")
        else item
    )
    require_athlete_access(block.athlete_id)
    return item


def coach_athlete_ids_query(user_id: int):
    """Compatibility-shaped query, constrained by the request's trusted context."""
    query = CoachAthleteOwnership.query.with_entities(
        CoachAthleteOwnership.athlete_id
    )
    try:
        context = current_tenancy_context()
    except (TenancyResolutionError, RuntimeError):
        return query.filter(false())
    if context.user_id != user_id:
        return query.filter(false())
    return query.filter(
        CoachAthleteOwnership.organisation_id == context.organisation_id,
        CoachAthleteOwnership.coach_membership_id == context.membership_id,
        CoachAthleteOwnership.status == OwnershipStatus.ACTIVE,
    )


def owned_athlete_ids(user_id: int) -> tuple[int, ...]:
    return tuple(row[0] for row in coach_athlete_ids_query(user_id).distinct().all())


def coach_owns_athlete(user_id: int, athlete_id: int) -> bool:
    return coach_owns_athlete_in_organisation(user_id, athlete_id) is not None


def coach_owns_athlete_in_organisation(
    user_id: int, athlete_id: int, organisation_id: int | None = None
) -> int | None:
    try:
        context = current_tenancy_context()
    except (TenancyResolutionError, RuntimeError):
        return None
    if context.user_id != user_id or (
        organisation_id is not None and context.organisation_id != organisation_id
    ):
        return None
    row = coach_athlete_ids_query(user_id).filter(
        CoachAthleteOwnership.athlete_id == athlete_id
    ).first()
    return context.organisation_id if row is not None else None


def athlete_belongs_to_organisation(athlete_id: int, organisation_id: int) -> bool:
    return (
        CoachAthleteOwnership.query.join(Organisation)
        .filter(
            CoachAthleteOwnership.athlete_id == athlete_id,
            CoachAthleteOwnership.organisation_id == organisation_id,
            CoachAthleteOwnership.status == OwnershipStatus.ACTIVE,
            Organisation.active.is_(True),
        )
        .first()
        is not None
    )


def organisation_membership_required(view):
    """Require active Organisation authority for a coach-facing request."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("current_user") is None:
            abort(401)
        try:
            current_tenancy_context()
        except TenancyResolutionError:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def organisation_roles_required(*roles: OrganisationRole):
    """Authorize using membership roles, never the platform ``User.role``."""
    allowed = frozenset(OrganisationRole(role) for role in roles)
    if not allowed:
        raise ValueError("at least one Organisation role is required")

    def decorator(view):
        @organisation_membership_required
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_tenancy_context().role not in allowed:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
