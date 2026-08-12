"""Cross-tenant authorization contracts for the multi-coach rollout.

The production schema does not yet have organisations or coach-to-athlete
membership.  ``TenantSeed`` therefore describes the intended ownership graph
alongside real database rows.  Tests marked with ``TENANCY_GAP`` are strict:
they document today's known exposure and become failures (XPASS) when a route
starts enforcing the contract, prompting removal of the mark.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.models.meal_plan import MealPlanTemplate
from portal.models.nutrition_prescription import NutritionMacroPrescription
from portal.models.programming import TrainingBlock, TrainingSession, TrainingWeek
from portal.models.user import User, UserRole


TENANCY_GAP = pytest.mark.xfail(
    strict=True,
    reason=(
        "organisation and coach-to-athlete membership do not exist yet; "
        "authenticated coaches currently have global athlete access"
    ),
)
FILE_ACCESS_GAP = pytest.mark.xfail(
    strict=True,
    reason=(
        "meal-plan PDF metadata and tenant-aware file-store abstraction do not "
        "exist yet; define both before adding file delivery"
    ),
)


@dataclass(frozen=True)
class OrganisationSeed:
    id: str
    name: str
    coach_id: int
    athlete_id: int


@dataclass(frozen=True)
class TenantSeed:
    organisation_a: OrganisationSeed
    organisation_b: OrganisationSeed
    block_b: int
    week_b: int
    session_b: int
    checkin_b: int
    macro_b: str
    meal_template_b: str


@pytest.fixture()
def tenant_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "cross-tenant-security-contract",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        coach_a = User(email="coach-a@north.test", role=UserRole.COACH, active=True)
        coach_b = User(email="coach-b@south.test", role=UserRole.COACH, active=True)
        athlete_a = Athlete(
            first_name="Alex",
            last_name="Stone",
            email="alex@north.test",
            bodyweight_kg=81.0,
            next_competition="North Open",
        )
        athlete_b = Athlete(
            first_name="Alex",
            last_name="Stone",
            email="alex@south.test",
            bodyweight_kg=93.0,
            next_competition="South Open PRIVATE",
        )
        db.session.add_all([coach_a, coach_b, athlete_a, athlete_b])
        db.session.flush()

        block_b = TrainingBlock(athlete=athlete_b, name="South private block")
        week_b = TrainingWeek(block=block_b, name="South private week", position=1)
        session_b = TrainingSession(
            week=week_b, name="South private session", position=1
        )
        checkin_b = WeeklyCheckin(
            athlete=athlete_b,
            week_ending=date(2026, 8, 9),
            training_included=True,
            training_notes="South private check-in",
        )
        macro_b = NutritionMacroPrescription(
            id="macro-south-private",
            athlete=athlete_b,
            effective_from=date(2026, 8, 1),
            calories=2400,
            protein_g=190,
            carbohydrate_g=260,
            fat_g=70,
            created_by=coach_b,
        )
        template_b = MealPlanTemplate(
            id="meal-south-private",
            coach_id=coach_b.id,
            revision=1,
            status="draft",
            name="South PDF metadata PRIVATE",
            payload={"days": [], "substitutions": [], "notes": "private"},
        )
        db.session.add_all(
            [
                block_b,
                checkin_b,
                macro_b,
                template_b,
                AthleteCheckinSettings(
                    athlete=athlete_a,
                    training_enabled=True,
                    nutrition_enabled=True,
                ),
                AthleteCheckinSettings(
                    athlete=athlete_b,
                    training_enabled=True,
                    nutrition_enabled=True,
                ),
            ]
        )
        db.session.commit()
        app.config["TENANT_SEED"] = TenantSeed(
            organisation_a=OrganisationSeed(
                "org-north", "North Strength", coach_a.id, athlete_a.id
            ),
            organisation_b=OrganisationSeed(
                "org-south", "South Strength", coach_b.id, athlete_b.id
            ),
            block_b=block_b.id,
            week_b=week_b.id,
            session_b=session_b.id,
            checkin_b=checkin_b.id,
            macro_b=macro_b.id,
            meal_template_b=template_b.id,
        )
    return app


def _coach_a_client(app):
    client = app.test_client()
    seed = app.config["TENANT_SEED"]
    with client.session_transaction() as signed_in:
        signed_in["user_id"] = seed.organisation_a.coach_id
        signed_in["authenticated_at"] = time.time()
        signed_in["csrf_token"] = "tenant-a-csrf"
    return client


@TENANCY_GAP
def test_coach_list_does_not_disclose_similarly_named_athlete_from_other_org(
    tenant_app,
):
    response = _coach_a_client(tenant_app).get("/athletes")
    assert response.status_code == 200
    assert b"alex@south.test" not in response.data


@TENANCY_GAP
def test_coach_cannot_read_other_org_athlete_profile_competition_or_bodyweight(
    tenant_app,
):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(
        f"/athletes/{seed.organisation_b.athlete_id}"
    )
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_mutate_other_org_athlete_profile_by_direct_id(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).post(
        f"/athletes/{seed.organisation_b.athlete_id}/onboarding/goals",
        data={"csrf_token": "tenant-a-csrf", "primary_goal": "tampered"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("resource", "path"),
    [
        ("block", "/programming/blocks/{block_b}"),
        ("week", "/programming/weeks/{week_b}"),
        ("session", "/programming/sessions/{session_b}"),
    ],
)
@TENANCY_GAP
def test_coach_cannot_read_other_org_programming_direct_ids(
    tenant_app, resource, path
):
    del resource
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(path.format(**vars(seed)))
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_mutate_other_org_programming_block_direct_id(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).post(
        f"/programming/blocks/{seed.block_b}/archive",
        data={"csrf_token": "tenant-a-csrf"},
    )
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_read_other_org_checkin_direct_id(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(f"/check-ins/{seed.checkin_b}")
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_mutate_other_org_checkin_direct_id(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).post(
        f"/check-ins/{seed.checkin_b}/review",
        data={"csrf_token": "tenant-a-csrf", "coach_notes": "cross-tenant"},
    )
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_read_other_org_macro_history(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(
        f"/athletes/{seed.organisation_b.athlete_id}/nutrition-prescriptions"
    )
    assert response.status_code == 404


@TENANCY_GAP
def test_coach_cannot_create_other_org_macro_prescription(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).post(
        f"/athletes/{seed.organisation_b.athlete_id}/nutrition-prescriptions",
        data={
            "csrf_token": "tenant-a-csrf",
            "effective_from": "2026-08-12",
            "calories": "2200",
            "protein_g": "180",
            "carbohydrate_g": "230",
            "fat_g": "65",
        },
    )
    assert response.status_code == 404


def test_meal_plan_template_direct_id_is_scoped_to_owning_coach(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(
        f"/coach/meal-plans/{seed.meal_template_b}/edit"
    )
    assert response.status_code == 404


@TENANCY_GAP
def test_meal_plan_list_does_not_disclose_other_org_pdf_metadata(tenant_app):
    response = _coach_a_client(tenant_app).get("/coach/meal-plans")
    assert response.status_code == 200
    assert b"South PDF metadata PRIVATE" not in response.data


@FILE_ACCESS_GAP
def test_meal_plan_file_store_requires_tenant_scoped_metadata_contract(tenant_app):
    store = tenant_app.extensions["meal_plan_file_store"]
    assert callable(store.open_for_coach)
    assert callable(store.open_for_athlete)


@TENANCY_GAP
def test_performance_api_conceals_other_org_athlete_direct_id(tenant_app):
    seed = tenant_app.config["TENANT_SEED"]
    response = _coach_a_client(tenant_app).get(
        f"/api/v1/athletes/{seed.organisation_b.athlete_id}/performance/charts"
    )
    assert response.status_code == 404
