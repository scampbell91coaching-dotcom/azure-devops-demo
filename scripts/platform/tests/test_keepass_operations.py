import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "scripts" / "platform"


def make_cli(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.log"
    cli = bin_dir / "keepassxc-cli"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        "IFS= read -r password\n"
        "[[ $password == test-master ]] || exit 9\n"
        "printf '%q ' \"$@\" >>\"$COMMAND_LOG\"; printf '\\n' >>\"$COMMAND_LOG\"\n"
        "cmd=$1; shift\n"
        "if [[ $cmd == ls && ${UNLOCK_FAIL:-0} == 1 && $# == 2 ]]; then exit 1; fi\n"
        "if [[ $cmd == show && ${SHOW_MISSING:-0} == 1 ]]; then exit 1; fi\n"
        "if [[ $cmd == show ]]; then printf 'Password: FAKE_SECRET\\n'; fi\n"
        "if [[ $cmd == ls && ${*: -1} == \"$FAIL_GROUP\" ]]; then exit 1; fi\n"
    )
    cli.chmod(0o755)
    return bin_dir, log


def run_with_tty(script_name: str, database: Path, bin_dir: Path, log: Path, **extra_env):
    if not shutil.which("script"):
        pytest.skip("util-linux script is required for controlling-terminal tests")
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "COMMAND_LOG": str(log),
        "FAIL_GROUP": "",
    } | extra_env
    command = f"{PLATFORM / script_name} {database}"
    return subprocess.run(
        ["script", "-qfec", command, "/dev/null"],
        input="test-master\n",
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_bootstrap_constructs_older_cli_commands_without_password(tmp_path):
    database = tmp_path / "database.kdbx"
    database.touch()
    bin_dir, log = make_cli(tmp_path)

    result = run_with_tty(
        "keepass-bootstrap.sh", database, bin_dir, log, SHOW_MISSING="1"
    )

    assert result.returncode == 0, result.stderr
    commands = log.read_text()
    assert f"ls -q {database}" in commands
    assert f"mkdir -q {database} 00\\ -\\ Recovery" in commands
    assert "add -q --username metadata --notes" in commands
    assert "test-master" not in commands
    assert "FAKE_SECRET" not in result.stdout + result.stderr


def test_validation_redacts_entry_output_and_reports_missing_group(tmp_path):
    database = tmp_path / "database.kdbx"
    database.touch()
    bin_dir, log = make_cli(tmp_path)

    result = run_with_tty(
        "keepass-validate.sh",
        database,
        bin_dir,
        log,
        FAIL_GROUP="04 - Database/PostgreSQL",
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "FAIL group     04 - Database/PostgreSQL" in output
    assert "FAKE_SECRET" not in output
    assert "Password:" not in output


def test_validation_reports_missing_metadata_without_entry_output(tmp_path):
    database = tmp_path / "database.kdbx"
    database.touch()
    bin_dir, log = make_cli(tmp_path)

    result = run_with_tty(
        "keepass-validate.sh", database, bin_dir, log, SHOW_MISSING="1"
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "FAIL metadata  00 - Recovery/KeePass Database Recovery" in output
    assert "FAKE_SECRET" not in output


def test_bootstrap_stops_after_unlock_failure(tmp_path):
    database = tmp_path / "database.kdbx"
    database.touch()
    bin_dir, log = make_cli(tmp_path)

    result = run_with_tty(
        "keepass-bootstrap.sh", database, bin_dir, log, UNLOCK_FAIL="1"
    )

    assert result.returncode == 1
    assert "database unlock failed" in result.stdout + result.stderr
    assert "mkdir" not in log.read_text()


def test_backup_atomically_replaces_and_restricts_permissions(tmp_path):
    source = tmp_path / "source.kdbx"
    source.write_bytes(b"not-a-real-database")
    destination_dir = tmp_path / "offline"
    destination_dir.mkdir()
    destination = destination_dir / "backup.kdbx"
    destination.write_bytes(b"old-verified-backup")

    result = subprocess.run(
        [PLATFORM / "keepass-backup.sh", source, destination],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600


def test_backup_refuses_repository_destination(tmp_path):
    source = tmp_path / "source.kdbx"
    source.touch()
    in_repo = ROOT / "forbidden-test-backup.kdbx"
    result = subprocess.run(
        [PLATFORM / "keepass-backup.sh", source, in_repo],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "repository destinations are forbidden" in result.stderr
    assert not in_repo.exists()

def test_backup_requires_explicit_destination():
    result = subprocess.run(
        [PLATFORM / "keepass-backup.sh", "/outside/source.kdbx"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "SOURCE.kdbx DESTINATION.kdbx" in result.stderr


def test_backup_fails_when_sha256_checksums_differ(tmp_path):
    source = tmp_path / "source.kdbx"
    source.write_bytes(b"not-a-real-database")
    destination = tmp_path / "backup.kdbx"
    destination.write_bytes(b"existing-valid-backup")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_sha = bin_dir / "sha256sum"
    fake_sha.write_text(
        "#!/usr/bin/env bash\n"
        "case ${*: -1} in *source.kdbx) printf 'aaaa  source\\n';; "
        "*) printf 'bbbb  destination\\n';; esac\n"
    )
    fake_sha.chmod(0o755)

    result = subprocess.run(
        [PLATFORM / "keepass-backup.sh", source, destination],
        text=True,
        capture_output=True,
        env=os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"},
        check=False,
    )

    assert result.returncode == 1
    assert "checksum verification failed" in result.stderr
    assert destination.read_bytes() == b"existing-valid-backup"
    assert list(tmp_path.glob(".backup.kdbx.tmp.*")) == []


def test_backup_fails_before_copy_when_checksum_tooling_is_missing(tmp_path):
    source = tmp_path / "source.kdbx"
    source.write_bytes(b"not-a-real-database")
    destination = tmp_path / "backup.kdbx"
    destination.write_bytes(b"existing-valid-backup")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bash").symlink_to(shutil.which("bash"))

    result = subprocess.run(
        [PLATFORM / "keepass-backup.sh", source, destination],
        text=True,
        capture_output=True,
        env=os.environ | {"PATH": str(bin_dir)},
        check=False,
    )

    assert result.returncode == 1
    assert "sha256sum or shasum is required" in result.stderr
    assert destination.read_bytes() == b"existing-valid-backup"
    assert list(tmp_path.glob(".backup.kdbx.tmp.*")) == []


def test_tracked_keepass_guard_rejects_force_added_database(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", repository], check=True)
    guard = repository / "check-no-keepass-files.sh"
    guard.write_bytes((PLATFORM / "check-no-keepass-files.sh").read_bytes())
    guard.chmod(0o755)
    database = repository / "forced.kdbx"
    database.write_bytes(b"not-a-real-database")
    subprocess.run(
        ["git", "-C", repository, "add", "-f", database.name], check=True
    )

    result = subprocess.run(
        [guard], cwd=repository, text=True, capture_output=True, check=False
    )

    assert result.returncode == 1
    assert "forced.kdbx" in result.stderr


def test_tracked_keepass_guard_accepts_repository():
    result = subprocess.run(
        [PLATFORM / "check-no-keepass-files.sh"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
