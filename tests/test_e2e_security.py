from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "support" / "security.py"
SPEC = importlib.util.spec_from_file_location("e2e_security", MODULE_PATH)
assert SPEC and SPEC.loader
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)


def _clear_portal_modules():
    for module_name in list(sys.modules):
        if module_name == "portal" or module_name.startswith("portal."):
            sys.modules.pop(module_name, None)


@pytest.fixture
def isolated_portal_import(monkeypatch):
    portal_root = Path(__file__).resolve().parents[1] / "platform-portal"
    _clear_portal_modules()
    monkeypatch.syspath_prepend(str(portal_root))
    try:
        yield
    finally:
        _clear_portal_modules()


def test_explicit_test_flag_and_run_token_are_required(monkeypatch):
    monkeypatch.delenv("E2E_TEST_ONLY", raising=False)
    monkeypatch.delenv("E2E_RUN_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="E2E_TEST_ONLY"):
        security.require_test_only_environment()

    monkeypatch.setenv("E2E_TEST_ONLY", "1")
    with pytest.raises(RuntimeError, match="E2E_RUN_TOKEN"):
        security.require_test_only_environment()


def test_launcher_refuses_before_importing_application_dependencies():
    launcher = MODULE_PATH.with_name("run_server.py")
    environment = os.environ.copy()
    environment.pop("E2E_TEST_ONLY", None)
    environment.pop("E2E_RUN_TOKEN", None)
    result = subprocess.run(
        [sys.executable, str(launcher)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "E2E_TEST_ONLY=1 is required" in result.stderr


@pytest.mark.parametrize("value", ["production", "prod", "staging", "shared"])
def test_shared_environment_markers_are_refused(monkeypatch, value):
    monkeypatch.setenv("E2E_TEST_ONLY", "1")
    monkeypatch.setenv("E2E_RUN_TOKEN", "a" * 32)
    monkeypatch.setenv("ENVIRONMENT", value)
    with pytest.raises(RuntimeError, match="shared environment"):
        security.require_test_only_environment()


def test_database_is_unique_and_disposable(tmp_path):
    first = security.create_disposable_database(tmp_path)
    second = security.create_disposable_database(tmp_path)
    assert first != second
    assert first.parent == tmp_path
    assert first.exists() and second.exists()


def test_production_app_has_no_e2e_route(isolated_portal_import, tmp_path):
    pytest.importorskip("flask")
    from portal import create_app

    database = tmp_path / "security.sqlite"
    app = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}"}
    )
    assert all(
        not rule.rule.startswith("/__e2e__") for rule in app.url_map.iter_rules()
    )
