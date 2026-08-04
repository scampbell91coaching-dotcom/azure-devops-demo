"""Fail-closed boundaries for the local-only browser-test launcher."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TOKEN_MIN_LENGTH = 32
PRODUCTION_MARKERS = ("ENVIRONMENT", "APP_ENV", "FLASK_ENV")


def require_test_only_environment() -> str:
    if os.getenv("E2E_TEST_ONLY") != "1":
        raise RuntimeError("E2E_TEST_ONLY=1 is required")
    for name in PRODUCTION_MARKERS:
        if os.getenv(name, "").strip().lower() in {"prod", "production", "staging", "shared"}:
            raise RuntimeError(f"refusing browser tests when {name} identifies a shared environment")
    token = os.getenv("E2E_RUN_TOKEN", "")
    if len(token) < TOKEN_MIN_LENGTH:
        raise RuntimeError("E2E_RUN_TOKEN must contain at least 32 characters")
    return token


def create_disposable_database(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="traditional-strength-e2e-", suffix=".sqlite", dir=directory)
    os.close(descriptor)
    return Path(name)
