import importlib.util
import os
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "promote_image.py"
SPEC = importlib.util.spec_from_file_location("promote_image", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_updates_only_helm_image_tag(tmp_path, monkeypatch):
    path = tmp_path / "values.yaml"
    path.write_text("other:\n  tag: keep\nimage:\n  repository: example\n  tag: old\ntail: true\n")
    monkeypatch.setitem(MODULE.TARGETS, "flask", (path, "helm"))
    MODULE.update("flask", "new")
    assert path.read_text() == "other:\n  tag: keep\nimage:\n  repository: example\n  tag: new\ntail: true\n"


def test_updates_helm_image_digest_without_rewriting_tag(tmp_path, monkeypatch):
    path = tmp_path / "values.yaml"
    path.write_text("image:\n  repository: example\n  tag: old\n  digest: ''\n")
    monkeypatch.setitem(MODULE.TARGETS, "flask", (path, "helm"))
    digest = "sha256:" + "a" * 64
    MODULE.update("flask", digest)
    assert path.read_text() == (
        f"image:\n  repository: example\n  tag: old\n  digest: {digest}\n"
    )


def test_private_update_requires_all_workload_references(tmp_path, monkeypatch):
    path = tmp_path / "manifest.yaml"
    collector = tmp_path / "collector.yaml"
    old = "stevedevopslab6280.azurecr.io/platform-portal-private:" + "a" * 40
    path.write_text(f"one: {old}\ntwo: {old}\n")
    collector.write_text(f"collector: {old}\n")
    monkeypatch.setitem(MODULE.TARGETS, "private-platform", ((path, collector), "private"))
    MODULE.update("private-platform", "registry/platform:new")
    assert path.read_text().count("registry/platform:new") == 2
    assert collector.read_text().count("registry/platform:new") == 1


def git(cwd, *args):
    return subprocess.run(("git", *args), cwd=cwd, check=True, text=True, capture_output=True)


def test_replays_on_advanced_main_and_preserves_other_promotion(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    runner = tmp_path / "runner"
    other = tmp_path / "other"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", str(remote), str(runner))
    (runner / "flask-app").mkdir()
    (runner / "lead-magnets-chart").mkdir()
    (runner / "flask-app/values-production.yaml").write_text("image:\n  tag: old\n")
    (runner / "lead-magnets-chart/values.yaml").write_text("image:\n  tag: old\n")
    git(runner, "add", ".")
    git(runner, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "initial")
    git(runner, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(other))

    original_run = MODULE.run
    first_push = True

    def race(*args, **kwargs):
        nonlocal first_push
        if args[:3] == ("git", "push", "origin") and first_push:
            first_push = False
            (other / "lead-magnets-chart/values.yaml").write_text("image:\n  tag: other-new\n")
            git(other, "add", ".")
            git(other, "-c", "user.name=other", "-c", "user.email=other@example.com", "commit", "-m", "other promotion")
            git(other, "push", "origin", "main")
        return original_run(*args, **kwargs)

    monkeypatch.setattr(MODULE, "run", race)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    previous = Path.cwd()
    os.chdir(runner)
    try:
        assert MODULE.promote("flask", "flask-new", "promote flask", 3) == "promoted"
        assert MODULE.promote("flask", "flask-new", "promote flask", 3) == "noop"
    finally:
        os.chdir(previous)

    git(other, "pull", "--ff-only")
    assert (other / "flask-app/values-production.yaml").read_text() == "image:\n  tag: flask-new\n"
    assert (other / "lead-magnets-chart/values.yaml").read_text() == "image:\n  tag: other-new\n"
