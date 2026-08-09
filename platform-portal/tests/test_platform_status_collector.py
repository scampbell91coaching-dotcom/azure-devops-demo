import json
import os

from portal.collectors.platform_status import atomic_write, sample_snapshot


def test_sample_collector_output_contract():
    data = sample_snapshot()
    assert data["generated_at"]
    assert set(data["summary"]) == {"pass", "warn", "fail"}
    assert isinstance(data["checks"], list)
    assert data["observability"]["metrics_api_available"] is True


def test_atomic_write_replaces_complete_document(tmp_path, monkeypatch):
    destination = tmp_path / "platform-status.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    replacements = []
    real_replace = os.replace

    def recording_replace(source, target):
        replacements.append((source, target, json.loads(open(source, encoding="utf-8").read())))
        real_replace(source, target)

    monkeypatch.setattr("portal.collectors.platform_status.os.replace", recording_replace)
    atomic_write(destination, sample_snapshot())
    assert len(replacements) == 1
    assert replacements[0][1] == destination
    assert json.loads(destination.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not list(tmp_path.glob(".platform-status.json.*"))
