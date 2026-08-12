from datetime import timedelta

import pytest

from portal import create_app
from portal.extensions import db
from portal.models import (Athlete, InvitationStatus, OrganisationInvitation,
    OrganisationMembership, OrganisationRole, User, UserRole)
from portal.services.organisation_invitations import (OrganisationInvitationError,
    accept_invitation, digest_invitation_token, issue_invitation, revoke_invitation)
from portal.services.organisation_onboarding import (OrganisationEntitlementDenied,
    assign_athlete, build_onboarding, create_organisation, require_capability, select_plan)


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context(): db.create_all()
    return app


def test_hardened_invitation_is_hashed_superseded_and_one_time(app):
    with app.app_context():
        owner = User(email="owner@example.test", role=UserRole.COACH)
        invitee = User(email="coach@example.test", role=UserRole.COACH)
        db.session.add_all((owner, invitee)); db.session.commit()
        organisation = create_organisation(name="North Barbell", owner=owner)
        issuer = OrganisationMembership.query.filter_by(user_id=owner.id).one()
        first = issue_invitation(organisation.id, invitee.email, OrganisationRole.COACH,
                                 issuer.id, lifetime=timedelta(days=1))
        second = issue_invitation(organisation.id, invitee.email, OrganisationRole.COACH,
                                  issuer.id, lifetime=timedelta(days=1))
        db.session.refresh(first.invitation)
        assert first.invitation.status == InvitationStatus.SUPERSEDED
        assert second.raw_token not in second.invitation.token_digest
        assert second.invitation.token_digest == digest_invitation_token(second.raw_token)
        accept_invitation(second.raw_token, invitee)
        with pytest.raises(OrganisationInvitationError): accept_invitation(second.raw_token, invitee)


def test_revoke_and_onboarding_entitlements_fail_closed(app):
    with app.app_context():
        owner = User(email="owner@example.test", role=UserRole.COACH)
        athlete = Athlete(first_name="Ada", last_name="Lift", email="ada@example.test")
        db.session.add_all((owner, athlete)); db.session.commit()
        organisation = create_organisation(name="Closed Barbell", owner=owner)
        membership = OrganisationMembership.query.filter_by(user_id=owner.id).one()
        issued = issue_invitation(organisation.id, "coach@example.test", OrganisationRole.COACH,
                                  membership.id, lifetime=timedelta(days=1))
        assert revoke_invitation(issued.invitation.id, membership.id)
        with pytest.raises(OrganisationEntitlementDenied): require_capability(organisation.id, "programming")
        assign_athlete(organisation=organisation, coach_membership=membership, athlete=athlete)
        assert build_onboarding(organisation, membership).current_step == "plan"
        select_plan(organisation=organisation, identifier="team")
        assert build_onboarding(organisation, membership).ready
        assert require_capability(organisation.id, "nutrition").allowed
        assert OrganisationInvitation.query.count() == 1
