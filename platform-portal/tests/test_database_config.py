from pathlib import Path

from portal.database_config import resolve_database_uri


def test_local_database_directory_is_created(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    uri = resolve_database_uri(
        application_root=tmp_path,
        local_filename="local.db",
    )

    assert uri == f"sqlite:///{tmp_path / 'data' / 'local.db'}"
    assert (tmp_path / "data").is_dir()


def test_configured_database_uri_does_not_touch_application_root(
    tmp_path: Path,
    monkeypatch,
):
    read_only_style_root = tmp_path / "app"
    configured_uri = "sqlite:////data/platform-history.db"

    monkeypatch.setenv("DATABASE_URL", configured_uri)

    uri = resolve_database_uri(
        application_root=read_only_style_root,
        local_filename="local.db",
    )

    assert uri == configured_uri
    assert not read_only_style_root.exists()


def test_public_database_can_use_pvc_uri(
    tmp_path: Path,
    monkeypatch,
):
    configured_uri = "sqlite:////data/leads.db"
    monkeypatch.setenv("DATABASE_URL", configured_uri)

    uri = resolve_database_uri(
        application_root=tmp_path / "read-only-app",
        local_filename="public-leads.db",
    )

    assert uri == configured_uri
    assert not (tmp_path / "read-only-app").exists()


def test_postgresql_database_url_uses_psycopg_driver(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://coach:secret@localhost/traditional_strength",
    )

    uri = resolve_database_uri(
        application_root=tmp_path,
        local_filename="local.db",
    )

    assert uri == ("postgresql+psycopg://coach:secret@localhost/traditional_strength")
