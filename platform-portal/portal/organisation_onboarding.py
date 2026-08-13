from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import roles_required
from .billing.entitlements import DEFAULT_PLANS
from .extensions import db
from .models.athlete import Athlete
from .models.organisation import Organisation, OrganisationRole
from .models.user import UserRole
from .services.organisation_invitations import OrganisationInvitationError
from .services.organisation_onboarding import (OrganisationAccessDenied,
    OrganisationEntitlementDenied, OrganisationOnboardingError, assign_athlete,
    build_onboarding, create_organisation, invite_coach, require_membership, select_plan)

organisation_onboarding_bp = Blueprint("organisation_onboarding", __name__)


def _owner(organisation_id: int):
    try: return require_membership(g.current_user.id, organisation_id, roles=frozenset({OrganisationRole.OWNER}))
    except OrganisationAccessDenied: abort(404)


@organisation_onboarding_bp.route("/organisation/onboarding", methods=["GET", "POST"])
@roles_required(UserRole.COACH)
def start():
    if request.method == "POST":
        try: organisation = create_organisation(name=request.form.get("name", ""), owner=g.current_user)
        except OrganisationOnboardingError as exc: abort(400, description=str(exc))
        return redirect(url_for("organisation_onboarding.detail", organisation_id=organisation.id))
    memberships = tuple(g.current_user.organisation_memberships.filter_by(status="active").all())
    return render_template("organisation/onboarding_start.html", memberships=memberships)


@organisation_onboarding_bp.get("/organisations/<int:organisation_id>/onboarding")
@roles_required(UserRole.COACH)
def detail(organisation_id: int):
    owner, organisation = _owner(organisation_id), db.session.get(Organisation, organisation_id)
    if organisation is None or not organisation.active: abort(404)
    return render_template("organisation/onboarding.html", onboarding=build_onboarding(organisation, owner), plans=DEFAULT_PLANS.values())


@organisation_onboarding_bp.post("/organisations/<int:organisation_id>/onboarding/coach-invitations")
@roles_required(UserRole.COACH)
def coach_invitation(organisation_id: int):
    owner, organisation = _owner(organisation_id), db.session.get(Organisation, organisation_id)
    if organisation is None: abort(404)
    email = request.form.get("email", "")
    try: invite_coach(organisation=organisation, inviter=owner, email=email)
    except (OrganisationInvitationError, OrganisationOnboardingError, ValueError) as exc: abort(400, description=str(exc))
    flash(f"Coach invitation created for {email.strip().casefold()}.", "success")
    return redirect(url_for("organisation_onboarding.detail", organisation_id=organisation_id))


@organisation_onboarding_bp.post("/organisations/<int:organisation_id>/onboarding/athletes")
@roles_required(UserRole.COACH)
def athlete(organisation_id: int):
    owner, organisation = _owner(organisation_id), db.session.get(Organisation, organisation_id)
    if organisation is None: abort(404)
    first, last, email = request.form.get("first_name", "").strip(), request.form.get("last_name", "").strip(), request.form.get("email", "").strip().casefold()
    if not first or not last or "@" not in email: abort(400, description="Enter the athlete's name and email address.")
    record = Athlete.query.filter(db.func.lower(Athlete.email) == email).first()
    if record is None:
        record = Athlete(first_name=first, last_name=last, email=email); db.session.add(record); db.session.flush()
    try: assign_athlete(organisation=organisation, coach_membership=owner, athlete=record)
    except OrganisationAccessDenied: db.session.rollback(); abort(404)
    except OrganisationEntitlementDenied as exc: db.session.rollback(); abort(403, description=exc.decision.reason)
    return redirect(url_for("organisation_onboarding.detail", organisation_id=organisation_id))


@organisation_onboarding_bp.post("/organisations/<int:organisation_id>/onboarding/plan")
@roles_required(UserRole.COACH)
def plan(organisation_id: int):
    owner, organisation = _owner(organisation_id), db.session.get(Organisation, organisation_id)
    if organisation is None: abort(404)
    if build_onboarding(organisation, owner).current_step == "athletes": abort(409, description="Assign at least one athlete first.")
    try: select_plan(organisation=organisation, identifier=request.form.get("plan", ""))
    except OrganisationOnboardingError as exc: abort(400, description=str(exc))
    return redirect(url_for("organisation_onboarding.detail", organisation_id=organisation_id))
