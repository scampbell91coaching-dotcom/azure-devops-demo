from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..models.platform_snapshot import PlatformSnapshot


class PlatformSnapshotRepository:
    def add(self, snapshot: PlatformSnapshot) -> PlatformSnapshot:
        db.session.add(snapshot)
        db.session.commit()
        return snapshot

    def latest(self) -> PlatformSnapshot | None:
        return PlatformSnapshot.query.order_by(
            PlatformSnapshot.recorded_at.desc()
        ).first()

    def list_recent(self, limit: int = 288) -> list[PlatformSnapshot]:
        return list(
            PlatformSnapshot.query.order_by(PlatformSnapshot.recorded_at.desc())
            .limit(limit)
            .all()
        )

    def list_since(self, hours: int = 24) -> list[PlatformSnapshot]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        return list(
            PlatformSnapshot.query.filter(PlatformSnapshot.recorded_at >= cutoff)
            .order_by(PlatformSnapshot.recorded_at.asc())
            .all()
        )
