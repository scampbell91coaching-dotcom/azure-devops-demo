import json
from datetime import datetime, timezone

import pytest

from portal import create_app
from portal.services.release_readiness import (
    ReleaseEvidenceError,
    ReleaseEvidenceService,
    parse_release_evidence,
)


def evidence_payload():
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "ready",
        "repository": {"branch": "main", "commit": "abc123", "dirty": False},
        "checks": [
            {
                "name": "pytest",
                "status": "pass",
                "mandatory": True,
                "summary": "tests passed",
            },
            {
                "name": "postgresql_tests",
                "status": "skipped",
                "mandatory": False,
                "summary": "not configured",
            },
        ],
    }


def write_evidence(root, payload):
    path = root / "evidence" / "release" / "release-evidence.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parser_separates_required_and_optional_checks():
    parsed = parse_release_evidence(evidence_payload())

    assert parsed["status"] == "ready"
    assert [check["name"] for check in parsed["required_checks"]] == ["pytest"]
    assert [check["name"] for check in parsed["optional_checks"]] == [
        "postgresql_tests"
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda payload: payload.update(status="unknown"),
        lambda payload: payload.update(checks="pass"),
        lambda payload: payload["repository"].pop("commit"),
        lambda payload: payload["checks"][0].update(mandatory="yes"),
    ],
)
def test_parser_rejects_invalid_evidence(change):
    payload = evidence_payload()
    change(payload)

    with pytest.raises(ReleaseEvidenceError):
        parse_release_evidence(payload)


def test_missing_evidence_fails_closed(tmp_path):
    result = ReleaseEvidenceService(tmp_path).load(
        now=datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
    )

    assert not result.available
    assert result.error == "Release evidence has not been generated."


def test_malformed_json_fails_closed(tmp_path):
    path = tmp_path / "evidence" / "release" / "release-evidence.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    result = ReleaseEvidenceService(tmp_path).load(
        now=datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
    )

    assert not result.available
    assert result.error == "Release evidence could not be read safely."


def test_page_renders_release_evidence(tmp_path):
    write_evidence(tmp_path, evidence_payload())
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "REPOSITORY_ROOT": tmp_path,
        }
    )

    response = app.test_client().get("/release-readiness")

    assert response.status_code == 200
    assert b"READY" in response.data
    assert b"main" in response.data
    assert b"abc123" in response.data
    assert b"Required checks" in response.data
    assert b"tests passed" in response.data
    assert b"Optional checks" in response.data
    assert b"not configured" in response.data


def test_page_renders_safe_state_for_invalid_evidence(tmp_path):
    payload = evidence_payload()
    payload["status"] = "surprise"
    write_evidence(tmp_path, payload)
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "REPOSITORY_ROOT": tmp_path,
        }
    )

    response = app.test_client().get("/release-readiness")

    assert response.status_code == 200
    assert b"NOT_READY" in response.data
    assert b"malformed or unsupported" in response.data
    assert b"surprise" not in response.data


def test_stale_evidence_fails_closed_but_remains_presentable(tmp_path):
    payload = evidence_payload()
    payload["generated_at"] = "2026-08-04T12:00:00Z"
    write_evidence(tmp_path, payload)

    result = ReleaseEvidenceService(tmp_path, max_age_seconds=60).load(
        now=datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
    )

    assert result.readiness == "not_ready"
    assert result.available
    assert result.freshness == "stale"
    assert result.evidence["repository"]["commit"] == "abc123"
    assert "stale" in result.error


def test_current_evidence_reports_current_freshness(tmp_path):
    payload = evidence_payload()
    payload["generated_at"] = "2026-08-04T12:59:30Z"
    write_evidence(tmp_path, payload)

    result = ReleaseEvidenceService(tmp_path, max_age_seconds=60).load(
        now=datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
    )

    assert result.available
    assert result.freshness == "current"
    assert result.readiness == "ready"


def test_unavailable_evidence_reports_unavailable_freshness(tmp_path):
    result = ReleaseEvidenceService(tmp_path, tmp_path / "missing.json").load()

    assert not result.available
    assert result.freshness == "unavailable"
    assert result.readiness == "not_ready"


@pytest.mark.parametrize("state", ["ready", "not_ready", "malformed", "stale"])
def test_dashboard_pages_share_readiness_contract(tmp_path, state):
    payload = evidence_payload()
    if state == "not_ready":
        payload["status"] = "not_ready"
    elif state == "malformed":
        payload.pop("schema_version")
    elif state == "stale":
        payload["generated_at"] = "2020-01-01T00:00:00Z"
    write_evidence(tmp_path, payload)
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "REPOSITORY_ROOT": tmp_path,
        }
    )

    client = app.test_client()
    release_page = client.get("/release-readiness")
    engineering_page = client.get("/engineering")
    engineering_api = client.get("/api/v1/engineering-overview")
    expected = "ready" if state == "ready" else "not_ready"

    assert release_page.status_code == engineering_page.status_code == 200
    assert engineering_api.get_json()["release"]["readiness"] == expected
    expected_label = b"READY" if expected == "ready" else b"NOT_READY"
    assert expected_label in release_page.data
    expected_overview_label = b"Ready" if expected == "ready" else b"Not ready"
    assert expected_overview_label in engineering_page.data
    if state == "stale":
        assert b"STALE" in release_page.data
        assert b"abc123" in release_page.data
