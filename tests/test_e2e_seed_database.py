from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PORTAL_ROOT = ROOT / "platform-portal"
SEED_PATH = ROOT / "e2e" / "support" / "seed_database.py"


def _clear_portal_modules():
    for module_name in list(sys.modules):
        if module_name == "portal" or module_name.startswith("portal."):
            sys.modules.pop(module_name, None)


@pytest.fixture
def isolated_portal_import(monkeypatch):
    _clear_portal_modules()
    monkeypatch.syspath_prepend(str(PORTAL_ROOT))
    try:
        yield
    finally:
        _clear_portal_modules()


def _load_seed_database():
    spec = importlib.util.spec_from_file_location("e2e_seed_database", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.seed_database


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("e2e_seed_reset", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_e2e_database_seeds_once_and_safe_repeat_is_idempotent(
    isolated_portal_import, tmp_path
):
    pytest.importorskip("flask")
    from portal import create_app
    from portal.extensions import db
    from portal.models.athlete import Athlete
    from portal.models.exercise_library import Exercise

    database = tmp_path / "e2e.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "LEGACY_STARTUP_INITIALIZATION": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        }
    )
    seed_database = _load_seed_database()

    with app.app_context():
        db.create_all()
        assert Exercise.query.count() == 0

    seed_database(app)
    seed_database(app)

    with app.app_context():
        exercises = Exercise.query.order_by(Exercise.id).all()
        assert {exercise.name for exercise in exercises} == {
            "Competition Squat",
            "Competition Bench Press",
            "Competition Deadlift",
            "Conventional Deadlift",
            "Sumo Deadlift",
            "Squat Named Row",
            "Lat Pulldown",
            "Cable Row",
            "Bulgarian Split Squat",
            "Weighted Plank",
            "Pause Squat",
            "Leg Extension",
            "Leg Curl",
            "Back Extension",
            "Dumbbell Lateral Raise",
            "Triceps Pushdown",
            "Dumbbell Curl",
            "Standing Calf Raise",
        }
        assert len(exercises) == 18
        assert Athlete.query.count() == 8

        tenant_a = db.session.get(Athlete, 1101)
        tenant_b = db.session.get(Athlete, 2101)
        assert tenant_a.email == "athlete.a.e2e@example.test"
        assert tenant_b.email == "athlete.b.e2e@example.test"

        from portal.models.user import User, UserRole

        expected_accounts = {
            "coach.e2e@example.test": UserRole.COACH,
            "coach.a.e2e@example.test": UserRole.COACH,
            "owner.b.e2e@example.test": UserRole.COACH,
            "coach.b.e2e@example.test": UserRole.COACH,
            "athlete.a.e2e@example.test": UserRole.ATHLETE,
            "athlete.b.e2e@example.test": UserRole.ATHLETE,
        }
        for email, role in expected_accounts.items():
            assert User.query.filter_by(email=email).one().user_role == role

        from portal.models.organisation import (
            CoachAthleteOwnership,
            Organisation,
            OrganisationMembership,
            OrganisationRole,
        )

        assert Organisation.query.count() == 2
        assert OrganisationMembership.query.count() == 4
        assert CoachAthleteOwnership.query.count() == 2
        tenant_a_org = Organisation.query.filter_by(
            slug="traditional-strength-e2e-a"
        ).one()
        tenant_a_owner = User.query.filter_by(email="coach.e2e@example.test").one()
        assert OrganisationMembership.query.filter_by(
            organisation_id=tenant_a_org.id,
            user_id=tenant_a_owner.id,
            role=OrganisationRole.OWNER,
        ).one()


def test_service_reset_is_idempotent_and_leaves_unrelated_athletes_unchanged(
    isolated_portal_import, tmp_path
):
    pytest.importorskip("flask")
    from datetime import UTC, datetime

    from portal import create_app
    from portal.extensions import db
    from portal.models.athlete import Athlete
    from portal.models.client_service import ClientServiceChange
    from portal.models.checkins import AthleteCheckinSettings

    database = tmp_path / "reset.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "LEGACY_STARTUP_INITIALIZATION": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        }
    )
    seed = _load_seed_module()
    seed.seed_database(app)

    with app.app_context():
        alex = db.session.get(Athlete, 101)
        alex_before = (alex.email, alex.bodyweight_kg)
        settings = AthleteCheckinSettings.query.filter_by(athlete_id=202).one()
        settings.nutrition_enabled = False
        db.session.add(
            ClientServiceChange(
                athlete_id=202,
                service="nutrition",
                value="no",
                effective_at=datetime.now(UTC),
            )
        )
        db.session.commit()

        seed.reset_fixture("services")
        seed.reset_fixture("services")

        assert ClientServiceChange.query.filter_by(athlete_id=202).count() == 0
        assert AthleteCheckinSettings.query.filter_by(
            athlete_id=202
        ).one().nutrition_enabled
        alex = db.session.get(Athlete, 101)
        assert (alex.email, alex.bodyweight_kg) == alex_before
