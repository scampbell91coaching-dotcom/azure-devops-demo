from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "support" / "security.py"
SPEC = importlib.util.spec_from_file_location("e2e_security", MODULE_PATH)
assert SPEC and SPEC.loader
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)


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


def test_production_app_has_no_e2e_route():
    pytest.importorskip("flask")
    portal_root = Path(__file__).resolve().parents[1] / "platform-portal"
    import sys

    sys.path.insert(0, str(portal_root))
    try:
        from portal import create_app

        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        assert all(not rule.rule.startswith("/__e2e__") for rule in app.url_map.iter_rules())
    finally:
        sys.path.remove(str(portal_root))
