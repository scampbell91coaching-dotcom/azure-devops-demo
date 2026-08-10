from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models.warmup import (
    WarmupAssignment, WarmupOverride, WarmupPlanSnapshot, WarmupPlanSnapshotStep,
    WarmupProtocol,
)

PHASE_LABELS = {10: "General preparation", 20: "Athlete preparation", 30: "Lift preparation", 40: "Barbell ramp"}


@dataclass(frozen=True)
class WarmupStepView:
    key: str
    phase: int
    name: str
    kind: str
    sets: int
    reps: int | None
    duration_seconds: int | None
    percentage: float | None
    load_kg: float | None
    rest_seconds: int | None
    notes: str | None
    source_type: str
    source_version: int | None

    @property
    def phase_label(self) -> str:
        return PHASE_LABELS[self.phase]

    @property
    def instruction(self) -> str:
        if self.kind == "duration":
            dosage = f"{self.duration_seconds} sec"
        elif self.kind == "barbell":
            target = f"{self.percentage:g}%" if self.percentage is not None else f"{self.load_kg:g} kg"
            dosage = f"{self.reps} reps at {target}"
        else:
            dosage = f"{self.reps} reps"
        prefix = f"{self.sets} sets × " if self.sets > 1 else ""
        rest = f" · rest {self.rest_seconds} sec" if self.rest_seconds is not None else ""
        return f"{prefix}{dosage}{rest}"


def resolve_warmup(athlete_id: int, session_id: int) -> tuple[WarmupStepView, ...]:
    assignments = (
        WarmupAssignment.query.options(
            selectinload(WarmupAssignment.protocol).selectinload(WarmupProtocol.steps)
        )
        .filter_by(athlete_id=athlete_id, session_id=session_id)
        .order_by(WarmupAssignment.id)
        .all()
    )
    steps: list[WarmupStepView] = []
    for assignment in assignments:
        for row in assignment.protocol.steps:
            steps.append(WarmupStepView(
                key=f"{assignment.protocol.stable_key}:{row.id}", phase=row.phase, name=row.name,
                kind=row.kind, sets=row.sets, reps=row.reps, duration_seconds=row.duration_seconds,
                percentage=row.percentage, load_kg=row.load_kg, rest_seconds=row.rest_seconds,
                notes=row.notes, source_type="warmup_protocol", source_version=assignment.protocol.version,
            ))
    for override in WarmupOverride.query.filter_by(athlete_id=athlete_id, session_id=session_id).order_by(WarmupOverride.id):
        if override.action == "remove":
            steps = [step for step in steps if step.key != override.target_key]
        else:
            steps.append(WarmupStepView(
                key=f"override:{override.id}", phase=override.phase, name=override.name,
                kind=override.kind, sets=override.sets, reps=override.reps,
                duration_seconds=override.duration_seconds, percentage=override.percentage,
                load_kg=override.load_kg, rest_seconds=override.rest_seconds, notes=override.notes,
                source_type="manual_override", source_version=None,
            ))
    return tuple(sorted(steps, key=lambda item: item.phase))


def athlete_warmup(athlete_id: int, session_id: int) -> tuple[WarmupStepView, ...]:
    snapshot = WarmupPlanSnapshot.query.filter_by(athlete_id=athlete_id, session_id=session_id).first()
    if snapshot is None:
        resolved = resolve_warmup(athlete_id, session_id)
        snapshot = WarmupPlanSnapshot(athlete_id=athlete_id, session_id=session_id)
        for position, item in enumerate(resolved, 1):
            snapshot.steps.append(WarmupPlanSnapshotStep(
                position=position, phase=item.phase, name=item.name, kind=item.kind, sets=item.sets,
                reps=item.reps, duration_seconds=item.duration_seconds, percentage=item.percentage,
                load_kg=item.load_kg, rest_seconds=item.rest_seconds, notes=item.notes,
                source_type=item.source_type, source_key=item.key, source_version=item.source_version,
            ))
        db.session.add(snapshot)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            snapshot = WarmupPlanSnapshot.query.filter_by(athlete_id=athlete_id, session_id=session_id).one()
    return tuple(WarmupStepView(
        key=row.source_key, phase=row.phase, name=row.name, kind=row.kind, sets=row.sets,
        reps=row.reps, duration_seconds=row.duration_seconds, percentage=row.percentage,
        load_kg=row.load_kg, rest_seconds=row.rest_seconds, notes=row.notes,
        source_type=row.source_type, source_version=row.source_version,
    ) for row in snapshot.steps)
