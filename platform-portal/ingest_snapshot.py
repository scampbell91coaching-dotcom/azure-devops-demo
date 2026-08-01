from __future__ import annotations

import json
import os
from pathlib import Path

from portal import create_app
from portal.services.snapshot_ingestion import SnapshotIngestionService

ROOT = Path(__file__).resolve().parent
STATUS_FILE = Path(
    os.getenv("PLATFORM_STATUS_FILE", ROOT / "data" / "platform-status.json")
)


def main() -> None:
    if not STATUS_FILE.exists():
        raise SystemExit(f"Missing platform status JSON: {STATUS_FILE}")

    with STATUS_FILE.open(encoding="utf-8") as handle:
        status = json.load(handle)

    app = create_app()
    with app.app_context():
        snapshot = SnapshotIngestionService().ingest(status)

    print(
        f"Snapshot inserted id={snapshot.id} "
        f"score={snapshot.platform_score} "
        f"time={snapshot.recorded_at.isoformat()}"
    )


if __name__ == "__main__":
    main()
