from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import event

from portal import create_app
from portal.extensions import db
from portal.models import (
    Athlete,
    CoachAthleteOwnership,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
    User,
    UserRole,
)
from portal.tenancy import (
    TenantObjectNotFound,
    TenancyResolutionError,
    current_tenancy_context,
    load_owned_athlete,
    load_tenant_object,
    organisation_roles_required,
    resolve_tenancy_context,
    tenant_scoped_query,
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
        event.listen(
            db.engine,
            "connect",
            lambda connection, _record: connection.execute(
                "PRAGMA foreign_keys=ON"
            ),
        )
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def tenancy_seed(app):
    with app.app_context():
        coach = User(email="coach@north.test", role=UserRole.COACH, active=True)
        north = Organisation(name="North Strength", slug="north")
        south = Organisation(name="South Strength", slug="south")
        db.session.add_all([coach, north, south])
        db.session.flush()
        north_member = OrganisationMembership(
            organisation_id=north.id,
            user_id=coach.id,
            role=OrganisationRole.COACH,
        )
        south_member = OrganisationMembership(
            organisation_id=south.id,
            user_id=coach.id,
            role=OrganisationRole.ADMIN,
        )
        db.session.add_all([north_member, south_member])
        db.session.flush()
        north_athlete = Athlete(
            first_name="North", last_name="Lifter", email="lifter@north.test"
        )
        south_athlete = Athlete(
            first_name="South", last_name="Lifter", email="lifter@south.test"
        )
        db.session.add_all([north_athlete, south_athlete])
        db.session.flush()
        db.session.add_all(
            [
                CoachAthleteOwnership(
                    organisation_id=north.id,
                    coach_membership_id=north_member.id,
                    athlete_id=north_athlete.id,
                ),
                CoachAthleteOwnership(
                    organisation_id=south.id,
                    coach_membership_id=south_member.id,
                    athlete_id=south_athlete.id,
                ),
            ]
        )
        db.session.commit()
        return {
            "coach_id": coach.id,
            "north_id": north.id,
            "south_id": south.id,
            "north_athlete_id": north_athlete.id,
            "south_athlete_id": south_athlete.id,
        }


def test_resolution_requires_selection_for_multiple_memberships(app, tenancy_seed):
    with app.app_context():
        coach = db.session.get(User, tenancy_seed["coach_id"])
        with pytest.raises(TenancyResolutionError):
            resolve_tenancy_context(coach)

        context = resolve_tenancy_context(
            coach, organisation_id=tenancy_seed["north_id"]
        )
        assert context.organisation_id == tenancy_seed["north_id"]
        assert context.role is OrganisationRole.COACH
        with pytest.raises(FrozenInstanceError):
            context.organisation_id = tenancy_seed["south_id"]


def test_resolution_rejects_inactive_membership_and_organisation(app, tenancy_seed):
    with app.app_context():
        coach = db.session.get(User, tenancy_seed["coach_id"])
        membership = OrganisationMembership.query.filter_by(
            organisation_id=tenancy_seed["north_id"], user_id=coach.id
        ).one()
        membership.status = "inactive"
        db.session.commit()
        with pytest.raises(TenancyResolutionError):
            resolve_tenancy_context(coach, organisation_id=tenancy_seed["north_id"])

        membership.status = "active"
        membership.organisation.active = False
        db.session.commit()
        with pytest.raises(TenancyResolutionError):
            resolve_tenancy_context(coach, organisation_id=tenancy_seed["north_id"])


def test_platform_coach_role_does_not_supply_organisation_authority(app, tenancy_seed):
    with app.app_context():
        unmembered = User(
            email="unmembered-coach@test", role=UserRole.COACH, active=True
        )
        db.session.add(unmembered)
        db.session.commit()
        with pytest.raises(TenancyResolutionError):
            resolve_tenancy_context(
                unmembered, organisation_id=tenancy_seed["north_id"]
            )


def test_owned_athlete_loader_conceals_other_organisation(app, tenancy_seed):
    with app.app_context():
        coach = db.session.get(User, tenancy_seed["coach_id"])
        context = resolve_tenancy_context(
            coach, organisation_id=tenancy_seed["north_id"]
        )
        owned = load_owned_athlete(context, tenancy_seed["north_athlete_id"])
        assert owned.id == tenancy_seed["north_athlete_id"]
        with pytest.raises(TenantObjectNotFound):
            load_owned_athlete(context, tenancy_seed["south_athlete_id"])


def test_generic_loader_is_tenant_qualified(app, tenancy_seed):
    with app.app_context():
        coach = db.session.get(User, tenancy_seed["coach_id"])
        context = resolve_tenancy_context(
            coach, organisation_id=tenancy_seed["north_id"]
        )
        membership = load_tenant_object(
            context, OrganisationMembership, context.membership_id
        )
        assert membership.organisation_id == tenancy_seed["north_id"]
        with pytest.raises(TenantObjectNotFound):
            load_tenant_object(
                context,
                OrganisationMembership,
                OrganisationMembership.query.filter_by(
                    organisation_id=tenancy_seed["south_id"]
                ).one().id,
            )
        with pytest.raises(TypeError):
            tenant_scoped_query(context, User)


def test_request_context_and_role_decorator_use_selected_membership(app, tenancy_seed):
    @app.get("/_test/organisation-admin")
    @organisation_roles_required(OrganisationRole.ADMIN)
    def organisation_admin():
        return str(current_tenancy_context().organisation_id)

    with app.test_request_context("/_test/organisation-admin"):
        coach = db.session.get(User, tenancy_seed["coach_id"])
        from flask import g, session

        g.current_user = coach
        session["organisation_id"] = tenancy_seed["south_id"]
        response = organisation_admin()
        assert response == str(tenancy_seed["south_id"])
