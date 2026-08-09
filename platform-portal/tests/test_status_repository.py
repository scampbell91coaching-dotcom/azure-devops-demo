import json
from datetime import datetime, timedelta, timezone

from portal.repositories.status_repository import JsonStatusRepository


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def write_snapshot(path, generated_at):
    path.write_text(json.dumps({"generated_at": generated_at, "score": 100, "checks": []}), encoding="utf-8")


def test_configured_current_snapshot(tmp_path):
    path = tmp_path / "status.json"
    write_snapshot(path, (NOW - timedelta(seconds=60)).isoformat())
    data = JsonStatusRepository(path, freshness_seconds=900, now=lambda: NOW).load()
    assert data["freshness"]["state"] == "current"
    assert data["score"] == 100


def test_stale_snapshot(tmp_path):
    path = tmp_path / "status.json"
    write_snapshot(path, (NOW - timedelta(seconds=901)).isoformat())
    data = JsonStatusRepository(path, freshness_seconds=900, now=lambda: NOW).load()
    assert data["freshness"]["state"] == "stale"


def test_missing_configured_snapshot_is_unavailable(tmp_path):
    data = JsonStatusRepository(tmp_path / "missing.json", now=lambda: NOW).load()
    assert data["freshness"]["state"] == "unavailable"
    assert data["score"] is None


def test_invalid_json_is_unavailable(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{", encoding="utf-8")
    data = JsonStatusRepository(path, now=lambda: NOW).load()
    assert data["freshness"]["state"] == "unavailable"
    assert data["checks"][0]["status"] == "FAIL"


def test_future_snapshot_is_not_treated_as_healthy(tmp_path):
    path = tmp_path / "status.json"
    write_snapshot(path, (NOW + timedelta(minutes=5)).isoformat())
    data = JsonStatusRepository(path, now=lambda: NOW).load()
    assert data["freshness"]["state"] == "unavailable"


def test_unset_default_path_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATFORM_STATUS_FILE", raising=False)
    repository = JsonStatusRepository(now=lambda: NOW)
    repository.path = tmp_path / "missing.json"
    assert repository.load()["freshness"]["state"] == "not_configured"


def test_repository_reads_platform_status_file_environment(tmp_path, monkeypatch):
    path = tmp_path / "configured.json"
    write_snapshot(path, NOW.isoformat())
    monkeypatch.setenv("PLATFORM_STATUS_FILE", str(path))
    assert JsonStatusRepository(now=lambda: NOW).load()["score"] == 100
