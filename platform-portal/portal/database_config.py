from __future__ import annotations

import os
from pathlib import Path


def resolve_database_uri(
    application_root: Path,
    local_filename: str,
    environment_variable: str = "DATABASE_URL",
) -> str:
    """Resolve the database URI for local and deployed environments.

    Kubernetes supplies DATABASE_URL pointing at a writable mounted volume,
    such as /data/platform-history.db. When that variable exists, the
    application must not attempt to create directories under /app because the
    container root filesystem is intentionally read-only.

    Local development does not normally provide DATABASE_URL, so the helper
    creates the repository-local data directory and returns a local SQLite URI.
    """

    configured_uri = os.getenv(environment_variable)

    if configured_uri:
        return configured_uri

    local_database = application_root / "data" / local_filename
    local_database.parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{local_database}"
