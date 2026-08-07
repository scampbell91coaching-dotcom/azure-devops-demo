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
        assert [exercise.name for exercise in exercises] == [
            "Competition Squat",
            "Lat Pulldown",
            "Cable Row",
            "Bulgarian Split Squat",
            "Weighted Plank",
        ]
        assert len(exercises) == 5
        assert Athlete.query.count() == 2
