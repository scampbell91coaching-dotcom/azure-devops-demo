from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from portal import create_app
from portal.extensions import db
from portal.models import (
    Athlete,
    CoachAthleteOwnership,
    InvitationStatus,
    Organisation,
    OrganisationInvitation,
    OrganisationMembership,
    OrganisationRole,
    User,
    UserRole,
)


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "LEGACY_STARTUP_INITIALIZATION": False,
        }
    )

    with app.app_context():
        event.listen(db.engine, "connect", lambda conn, _record: conn.execute("PRAGMA foreign_keys=ON"))
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _user(email: str) -> User:
    return User(email=email, role=UserRole.COACH, active=True)


def test_membership_is_unique_within_organisation_but_user_can_join_another(app):
    with app.app_context():
        user = _user("coach@example.test")
        first = Organisation(name="First", slug=" First ")
        second = Organisation(name="Second", slug="second")
        db.session.add_all([user, first, second])
        db.session.flush()
        db.session.add_all(
            [
                OrganisationMembership(organisation_id=first.id, user_id=user.id, role=OrganisationRole.OWNER),
                OrganisationMembership(organisation_id=second.id, user_id=user.id, role=OrganisationRole.COACH),
            ]
        )
        db.session.commit()
        assert first.slug == "first"

        db.session.add(OrganisationMembership(organisation_id=first.id, user_id=user.id, role=OrganisationRole.SUPPORT))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_ownership_rejects_coach_membership_from_another_organisation(app):
    with app.app_context():
        coach = _user("coach@example.test")
        athlete = Athlete(first_name="Ada", last_name="Lovelace", email="ada@example.test")
        first = Organisation(name="First", slug="first")
        second = Organisation(name="Second", slug="second")
        db.session.add_all([coach, athlete, first, second])
        db.session.flush()
        membership = OrganisationMembership(organisation_id=first.id, user_id=coach.id, role=OrganisationRole.COACH)
        db.session.add(membership)
        db.session.flush()
        db.session.add(CoachAthleteOwnership(organisation_id=second.id, coach_membership_id=membership.id, athlete_id=athlete.id))

        with pytest.raises(IntegrityError):
            db.session.commit()


def test_invitation_lifecycle_checks_email_and_expiry(app):
    with app.app_context():
        user = _user("NEW.COACH@example.test")
        inviter = _user("owner@example.test")
        organisation = Organisation(name="Club", slug="club")
        db.session.add_all([user, inviter, organisation])
        db.session.flush()
        membership = OrganisationMembership(organisation_id=organisation.id, user_id=inviter.id, role=OrganisationRole.OWNER)
        db.session.add(membership)
        db.session.flush()
        invitation = OrganisationInvitation(
            organisation_id=organisation.id,
            email_normalised=" New.Coach@Example.Test ",
            role=OrganisationRole.COACH,
            token_digest="a" * 64,
            invited_by_membership_id=membership.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        invitation.accept(user)
        db.session.add(invitation)
        db.session.commit()

        assert invitation.email_normalised == "new.coach@example.test"
        assert invitation.status == InvitationStatus.ACCEPTED
        assert invitation.accepted_by_user_id == user.id
        with pytest.raises(ValueError, match="Only pending"):
            invitation.revoke()


def test_only_one_pending_invitation_per_org_and_email(app):
    with app.app_context():
        inviter = _user("owner@example.test")
        organisation = Organisation(name="Club", slug="club")
        db.session.add_all([inviter, organisation])
        db.session.flush()
        membership = OrganisationMembership(organisation_id=organisation.id, user_id=inviter.id, role=OrganisationRole.OWNER)
        db.session.add(membership)
        db.session.flush()
        kwargs = {
            "organisation_id": organisation.id,
            "email_normalised": "coach@example.test",
            "role": OrganisationRole.COACH,
            "invited_by_membership_id": membership.id,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        db.session.add_all([
            OrganisationInvitation(token_digest="a" * 64, **kwargs),
            OrganisationInvitation(token_digest="b" * 64, **kwargs),
        ])
        with pytest.raises(IntegrityError):
            db.session.commit()
