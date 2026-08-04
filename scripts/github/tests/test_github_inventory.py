import importlib.util
import json
import os
import stat
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "github_inventory.py"
SPEC = importlib.util.spec_from_file_location("github_inventory", MODULE_PATH)
github_inventory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = github_inventory
SPEC.loader.exec_module(github_inventory)


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.commands = []

    def __call__(self, command, cwd):
        self.commands.append((list(command), cwd))
        for match, result in self.responses:
            if match(command):
                return result
        raise AssertionError(f"unexpected command: {command}")


def result(payload=None, returncode=0, stderr=""):
    stdout = json.dumps(payload) if payload is not None else ""
    return github_inventory.CommandResult(returncode, stdout, stderr)


def endpoint_ends(suffix):
    return lambda command: command[:4] == ["gh", "api", "--method", "GET"] and command[4].endswith(suffix)


def successful_runner():
    return FakeRunner([
        (lambda c: c == ["gh", "auth", "status"], result()),
        (lambda c: c[:3] == ["gh", "repo", "view"], result({
            "nameWithOwner": "acme/widgets", "url": "https://github.example/acme/widgets",
            "defaultBranchRef": {"name": "main"}, "isPrivate": True, "visibility": "PRIVATE",
        })),
        (endpoint_ends("actions/workflows"), result([{"workflows": [{"id": 7, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}]}])),
        (endpoint_ends("actions/variables"), result([{"variables": [{"name": "REGION", "value": "must-not-leak", "updated_at": "today"}]}])),
        (endpoint_ends("actions/secrets"), result([{"secrets": [{"name": "DEPLOY_TOKEN", "created_at": "yesterday"}]}])),
        (endpoint_ends("environments"), result([{"environments": [{"name": "prod/eu", "protection_rules": []}]}])),
        (endpoint_ends("environments/prod%2Feu/secrets"), result([{"secrets": [{"name": "AZURE_ID"}]}])),
        (endpoint_ends("branches/main/protection"), result({"enforce_admins": {"enabled": True}, "unexpected_token": "leak"})),
    ])


def test_constructs_read_only_commands_and_defaults_to_current_repository(tmp_path):
    runner = successful_runner()
    data = github_inventory.InventoryCollector(tmp_path, runner=runner).collect()

    commands = [command for command, cwd in runner.commands]
    assert commands[1] == ["gh", "repo", "view", "--json", "nameWithOwner,url,defaultBranchRef,isPrivate,visibility"]
    assert all(cwd == tmp_path for _, cwd in runner.commands)
    assert all("--method" not in command or command[command.index("--method") + 1] == "GET" for command in commands)
    assert not any(any(word in command for word in ("POST", "PUT", "PATCH", "DELETE")) for command in commands)
    assert data["status"] == "ok"


def test_parses_names_metadata_and_redacts_values(tmp_path):
    data = github_inventory.InventoryCollector(tmp_path, runner=successful_runner()).collect()

    assert data["variables"]["items"] == [{"name": "REGION", "updated_at": "today"}]
    assert data["secrets"]["items"][0]["name"] == "DEPLOY_TOKEN"
    assert data["environments"]["items"][0]["secrets"]["items"] == [{"name": "AZURE_ID"}]
    serialized = json.dumps(data)
    assert "must-not-leak" not in serialized
    assert "unexpected_token" not in serialized
    assert "leak" not in serialized


def test_empty_and_unauthorized_sections_are_distinct(tmp_path):
    runner = successful_runner()
    runner.responses.insert(0, (endpoint_ends("actions/variables"), result([{"variables": []}])))
    runner.responses.insert(0, (endpoint_ends("actions/secrets"), result(returncode=1, stderr="HTTP 403: Resource not accessible")))
    data = github_inventory.InventoryCollector(tmp_path, runner=runner).collect()

    assert data["variables"] == {"status": "empty", "items": []}
    assert data["secrets"]["status"] == "unauthorized"
    assert "403" not in data["secrets"]["detail"]


def test_authentication_failure_stops_before_metadata_calls(tmp_path):
    runner = FakeRunner([
        (lambda c: c == ["gh", "auth", "status"], result(returncode=1, stderr="not logged into any GitHub hosts")),
    ])
    data = github_inventory.InventoryCollector(tmp_path, runner=runner).collect()

    assert data["status"] == "unauthenticated"
    assert len(runner.commands) == 1


def test_invalid_json_is_unavailable(tmp_path):
    runner = successful_runner()
    runner.responses.insert(0, (endpoint_ends("actions/workflows"), github_inventory.CommandResult(0, "not-json", "")))
    data = github_inventory.InventoryCollector(tmp_path, runner=runner).collect()

    assert data["workflows"]["status"] == "unavailable"


def test_missing_repository_identity_is_unavailable(tmp_path):
    runner = FakeRunner([
        (lambda c: c == ["gh", "auth", "status"], result()),
        (lambda c: c[:3] == ["gh", "repo", "view"], result({"defaultBranchRef": {"name": "main"}})),
    ])

    data = github_inventory.InventoryCollector(tmp_path, runner=runner).collect()

    assert data["status"] == "unavailable"
    assert len(runner.commands) == 2


def test_branch_protection_distinguishes_unprotected_from_unavailable(tmp_path):
    runner = successful_runner()
    runner.responses.insert(0, (
        endpoint_ends("branches/main/protection"),
        result(returncode=1, stderr="HTTP 404: Branch not protected"),
    ))
    assert github_inventory.InventoryCollector(tmp_path, runner=runner).collect()["default_branch_protection"]["status"] == "empty"

    runner = successful_runner()
    runner.responses.insert(0, (
        endpoint_ends("branches/main/protection"),
        result(returncode=1, stderr="HTTP 404: Not Found"),
    ))
    assert github_inventory.InventoryCollector(tmp_path, runner=runner).collect()["default_branch_protection"]["status"] == "unavailable"


def test_repo_override_is_passed_only_to_repo_view(tmp_path):
    runner = successful_runner()
    github_inventory.InventoryCollector(tmp_path, runner=runner, repo="other/project").collect()

    assert runner.commands[1][0][3] == "other/project"
    assert any("repos/acme/widgets/actions/workflows" in command for command, _ in runner.commands)


def test_recursive_sanitizer_removes_sensitive_fields():
    clean = github_inventory.sanitize({
        "name": "ok", "secrets": {"items": [{"name": "SAFE_NAME"}]},
        "nested": {"password": "bad", "apiToken": "bad", "client_secret": "bad"},
        "value": "bad",
    })
    assert clean == {"name": "ok", "nested": {}}


def test_recursive_sanitizer_drops_nested_secrets_value():
    marker = "must-not-survive"

    assert github_inventory.sanitize({"nested": {"secrets": {"value": marker}}}) == {"nested": {}}


def test_shared_contract_has_canonical_repository_and_environment_scopes(tmp_path):
    data = github_inventory.InventoryCollector(tmp_path, runner=successful_runner()).collect()

    contract = github_inventory.build_secret_name_inventory(data)

    assert contract["schema_version"] == "1.0"
    assert contract["source"] == "github"
    assert contract["collection_status"] == "complete"
    assert contract["secret_scopes"] == [
        {
            "scope": {"repository": "acme/widgets", "environment": None, "subscription": None, "resource_group": None, "key_vault": None},
            "coverage": "complete", "secret_names": ["DEPLOY_TOKEN"],
        },
        {
            "scope": {"repository": "acme/widgets", "environment": "prod/eu", "subscription": None, "resource_group": None, "key_vault": None},
            "coverage": "complete", "secret_names": ["AZURE_ID"],
        },
    ]
    assert "created_at" not in json.dumps(contract)


def test_shared_contract_marks_unavailable_name_collection_unknown(tmp_path):
    runner = successful_runner()
    runner.responses.insert(0, (endpoint_ends("actions/secrets"), result(returncode=1, stderr="HTTP 403")))
    contract = github_inventory.build_secret_name_inventory(
        github_inventory.InventoryCollector(tmp_path, runner=runner).collect()
    )

    assert contract["collection_status"] == "partial"
    assert contract["secret_scopes"][0]["coverage"] == "unknown"
    assert contract["secret_scopes"][0]["secret_names"] == []


def test_main_writes_private_reports_atomically_under_umask_022(tmp_path, monkeypatch):
    monkeypatch.setattr(github_inventory.shutil, "which", lambda command: None)
    output = tmp_path / "reports"
    previous_umask = os.umask(0o022)
    try:
        result_code = github_inventory.main(["--repo-root", str(tmp_path), "--output-dir", str(output)])
    finally:
        os.umask(previous_umask)

    assert result_code == github_inventory.EXIT_ERROR
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert {path.name for path in output.iterdir()} == {
        "github-inventory.json", "github-inventory.md", "github-secret-name-inventory.json",
    }
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())
    assert not any(path.name.startswith(".") for path in output.iterdir())


def test_producer_fixture_matches_generated_contract_shape(tmp_path):
    data = github_inventory.InventoryCollector(tmp_path, runner=successful_runner()).collect()
    data["generated_at"] = "2026-08-04T12:00:00Z"
    fixture = Path(__file__).parent / "fixtures" / "github-secret-name-inventory.v1.json"

    assert json.loads(fixture.read_text(encoding="utf-8")) == github_inventory.build_secret_name_inventory(data)


def test_markdown_escapes_untrusted_names():
    data = github_inventory.InventoryCollector(Path("/tmp"), runner=successful_runner()).collect()
    data["workflows"]["items"][0]["name"] = "CI`\nInjected"

    report = github_inventory.render_markdown(data)

    assert "`CI' Injected`" in report
