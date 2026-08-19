#!/usr/bin/env python3
"""Fail-closed, Azure-read-only restore drill preflight and timing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PRODUCTION_RE = re.compile(r"(^|[.\-_/])(prod(uction)?|live)([.\-_/]|$)", re.I)
DISPOSABLE_RE = re.compile(r"(^|[.\-_/])(restore|drill|disposable|sandbox)([.\-_/]|$)", re.I)


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def validate(source_id: str, target_id: str, source_host: str, target_host: str) -> list[dict]:
    pairs = (("resource_id", source_id, target_id), ("hostname", source_host, target_host))
    checks = []
    for label, source, target in pairs:
        checks.append({"name": f"different_{label}", "ok": source.casefold().rstrip(".") != target.casefold().rstrip("."), "detail": "source and target differ"})
    identity = f"{target_id}/{target_host}"
    checks.append({"name": "target_not_production_named", "ok": not bool(PRODUCTION_RE.search(identity)), "detail": "target does not match prod/production/live tokens"})
    checks.append({"name": "target_explicitly_disposable", "ok": bool(DISPOSABLE_RE.search(identity)), "detail": "target matches restore/drill/disposable/sandbox token"})
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rehearsal-id", "source-resource-id", "target-resource-id", "source-host", "target-host", "requested-restore-point", "restore-started-at"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--restore-ready-at")
    parser.add_argument("--validation-finished-at")
    parser.add_argument("--rpo-minutes", type=int, default=15)
    parser.add_argument("--rto-minutes", type=int, default=240)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = validate(args.source_resource_id, args.target_resource_id, args.source_host, args.target_host)
    requested, started = utc(args.requested_restore_point), utc(args.restore_started_at)
    ready = utc(args.restore_ready_at) if args.restore_ready_at else None
    finished = utc(args.validation_finished_at) if args.validation_finished_at else None
    rpo = (started - requested).total_seconds() / 60
    rto = (finished - started).total_seconds() / 60 if finished else None
    checks += [
        {"name": "restore_point_precedes_start", "ok": 0 <= rpo, "detail": f"minutes={rpo:.2f}"},
        {"name": "rpo_objective", "ok": 0 <= rpo <= args.rpo_minutes, "detail": f"minutes={rpo:.2f}, objective={args.rpo_minutes}"},
        {"name": "time_order", "ok": (not ready or ready >= started) and (not finished or (ready or started) <= finished), "detail": "timestamps are chronological"},
        {"name": "rto_objective", "ok": rto is None or rto <= args.rto_minutes, "detail": "pending" if rto is None else f"minutes={rto:.2f}, objective={args.rto_minutes}"},
    ]
    result = {
        "schema": "traditional-strength.restore-preflight.v1", "rehearsal_id": args.rehearsal_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": hashlib.sha256(args.source_resource_id.encode()).hexdigest()[:12],
        "target_fingerprint": hashlib.sha256(args.target_resource_id.encode()).hexdigest()[:12],
        "timing": {"requested_restore_point": requested.isoformat(), "restore_started_at": started.isoformat(), "restore_ready_at": ready.isoformat() if ready else None, "validation_finished_at": finished.isoformat() if finished else None, "rpo_minutes": round(rpo, 2), "rto_minutes": round(rto, 2) if rto is not None else None},
        "checks": checks, "passed": all(item["ok"] for item in checks),
    }
    path = Path(args.output)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temp.replace(path)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
