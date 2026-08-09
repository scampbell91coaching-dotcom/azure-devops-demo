import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_warmup_migration_upgrades_and_downgrades_cleanly(tmp_path):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database}", "SECRET_KEY": "migration-test"}
    command = [sys.executable, "-m", "flask", "--app", "portal:create_app", "db"]
    subprocess.run([*command, "upgrade"], cwd=root, env=env, check=True, capture_output=True, text=True)
    tables = set(inspect(create_engine(env["DATABASE_URL"])).get_table_names())
    assert {"warmup_protocols", "warmup_protocol_steps", "warmup_assignments", "warmup_overrides", "warmup_plan_snapshots", "warmup_plan_snapshot_steps"} <= tables
    subprocess.run([*command, "downgrade", "0013_accessory_intelligence"], cwd=root, env=env, check=True, capture_output=True, text=True)
    tables = set(inspect(create_engine(env["DATABASE_URL"])).get_table_names())
    assert not any(name.startswith("warmup_") for name in tables)
