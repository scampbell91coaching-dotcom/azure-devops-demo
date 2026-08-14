import json

import pytest

from portal import create_app
from portal.extensions import db
from portal.models import (
    Athlete,
    CoachAthleteOwnership,
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
    OwnershipStatus,
    User,
    UserRole,
)
from portal.services.canonical_tenancy_reconciliation import (
    reconcile_canonical_tenancy,
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
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _single_tenant(*, membership_status=None, ownership_status=None):
    organisation = Organisation(name="Legacy Strength", slug="legacy-strength")
    coach = User(email="coach@example.test", role=UserRole.COACH, active=True)
    athlete = Athlete(first_name="Test", last_name="Athlete", email="athlete@example.test")
    db.session.add_all([organisation, coach, athlete])
    db.session.flush()
    membership = None
    if membership_status is not None:
        membership = OrganisationMembership(
            organisation_id=organisation.id,
            user_id=coach.id,
            role=OrganisationRole.OWNER,
            status=membership_status,
        )
        db.session.add(membership)
        db.session.flush()
    if ownership_status is not None:
        db.session.add(
            CoachAthleteOwnership(
                organisation_id=organisation.id,
                coach_membership_id=membership.id,
                athlete_id=athlete.id,
                status=ownership_status,
            )
        )
    db.session.commit()
    return organisation, coach, athlete, membership


def test_no_organisation_is_actionable_refusal(app):
    with app.app_context():
        db.session.add(User(email="coach@example.test", role=UserRole.COACH))
        db.session.commit()

        report = reconcile_canonical_tenancy()

        assert report.status == "refused"
        assert "No organisation exists" in report.blockers[0]


def test_missing_membership_and_ownership_are_dry_run_by_default(app):
    with app.app_context():
        _, _, athlete, _ = _single_tenant()

        report = reconcile_canonical_tenancy()

        assert report.status == "changes-required"
        assert report.missing_membership is True
        assert report.missing_ownership_athlete_ids == [athlete.id]
        assert OrganisationMembership.query.count() == 0
        assert CoachAthleteOwnership.query.count() == 0


def test_missing_membership_is_created_as_owner_on_apply(app):
    with app.app_context():
        organisation, coach, _, _ = _single_tenant()

        report = reconcile_canonical_tenancy(apply=True)

        membership = OrganisationMembership.query.one()
        assert report.status == "applied"
        assert membership.organisation_id == organisation.id
        assert membership.user_id == coach.id
        assert membership.role == OrganisationRole.OWNER
        assert membership.status == MembershipStatus.ACTIVE


def test_missing_ownership_is_created_for_existing_membership(app):
    with app.app_context():
        organisation, _, athlete, membership = _single_tenant(
            membership_status=MembershipStatus.ACTIVE
        )

        report = reconcile_canonical_tenancy(apply=True)

        ownership = CoachAthleteOwnership.query.one()
        assert report.changes_applied == 1
        assert ownership.organisation_id == organisation.id
        assert ownership.coach_membership_id == membership.id
        assert ownership.athlete_id == athlete.id


def test_already_healthy_state_has_no_changes(app):
    with app.app_context():
        _single_tenant(
            membership_status=MembershipStatus.ACTIVE,
            ownership_status=OwnershipStatus.ACTIVE,
        )

        report = reconcile_canonical_tenancy(apply=True)

        assert report.status == "healthy"
        assert report.changes_applied == 0


def test_multi_organisation_state_is_ambiguous_and_unchanged(app):
    with app.app_context():
        _single_tenant()
        db.session.add(Organisation(name="Other", slug="other"))
        db.session.commit()

        report = reconcile_canonical_tenancy(apply=True)

        assert report.status == "refused"
        assert "exactly one active organisation" in report.blockers[0]
        assert OrganisationMembership.query.count() == 0


@pytest.mark.parametrize(
    ("membership_status", "ownership_status", "expected"),
    [
        (MembershipStatus.INACTIVE, None, "Membership"),
        (MembershipStatus.ACTIVE, OwnershipStatus.INACTIVE, "Inactive ownerships"),
    ],
)
def test_inactive_lifecycle_rows_are_never_reactivated(
    app, membership_status, ownership_status, expected
):
    with app.app_context():
        _single_tenant(
            membership_status=membership_status,
            ownership_status=ownership_status,
        )

        report = reconcile_canonical_tenancy(apply=True)

        assert report.status == "refused"
        assert expected in report.blockers[0]
        membership = OrganisationMembership.query.one()
        assert membership.status == membership_status
        if ownership_status is not None:
            assert CoachAthleteOwnership.query.one().status == ownership_status


def test_apply_and_dry_run_are_idempotent(app):
    with app.app_context():
        _single_tenant()

        first = reconcile_canonical_tenancy(apply=True)
        second = reconcile_canonical_tenancy(apply=True)
        dry_run = reconcile_canonical_tenancy()

        assert first.changes_applied == 2
        assert second.status == "healthy"
        assert second.changes_applied == 0
        assert dry_run.status == "healthy"
        assert OrganisationMembership.query.count() == 1
        assert CoachAthleteOwnership.query.count() == 1


def test_cli_defaults_to_dry_run_and_requires_apply_to_mutate(app):
    with app.app_context():
        _single_tenant()
    runner = app.test_cli_runner()

    dry_result = runner.invoke(args=["reconcile-canonical-tenancy"])
    with app.app_context():
        assert json.loads(dry_result.output)["mode"] == "dry-run"
        assert OrganisationMembership.query.count() == 0

    apply_result = runner.invoke(args=["reconcile-canonical-tenancy", "--apply"])
    with app.app_context():
        assert apply_result.exit_code == 0
        assert json.loads(apply_result.output)["changes_applied"] == 2
        assert OrganisationMembership.query.count() == 1
