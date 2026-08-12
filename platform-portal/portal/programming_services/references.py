"""Deterministic, athlete-scoped programme reference and comparison services.

This module deliberately does not copy, save, or publish programmes.  It turns a
historical block into a semantic (database-id-free) coaching reference and
compares a separately authored proposal with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import selectinload

from ..models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)


class ReferenceResolutionError(ValueError):
    """Raised when an athlete's requested reference is absent or ambiguous."""


class ReferenceIsolationError(ValueError):
    """Raised before comparing blocks belonging to different athletes."""


PRESERVED_ELEMENTS = (
    "split",
    "lift_exposure_frequency",
    "lift_variations",
    "progression_shape",
)
ELIGIBLE_TO_CHANGE = (
    "block_metadata",
    "session_notes",
    "prescription_targets",
)


@dataclass(frozen=True)
class ProposalChange:
    path: str
    reference: Any
    proposal: Any
    policy: str


@dataclass(frozen=True)
class ProposalDiff:
    reference_block_id: int
    proposal_block_id: int
    changes: tuple[ProposalChange, ...]

    @property
    def preserved_changes(self) -> tuple[ProposalChange, ...]:
        return tuple(change for change in self.changes if change.policy == "preserved")

    @property
    def eligible_changes(self) -> tuple[ProposalChange, ...]:
        return tuple(change for change in self.changes if change.policy == "eligible_to_change")


def resolve_reference_block(
    athlete_id: int,
    *,
    block_id: int | None = None,
    name: str | None = None,
    exclude_block_id: int | None = None,
) -> TrainingBlock:
    """Resolve exactly one explicitly selected block, scoped to one athlete.

    Error text intentionally does not reveal whether a similarly named/id'd
    block exists for another athlete.
    """
    cleaned_name = name.strip() if name is not None else None
    if (block_id is None) == (not cleaned_name):
        raise ReferenceResolutionError("Select one previous block by id or name.")

    query = TrainingBlock.query.options(
        selectinload(TrainingBlock.weeks)
        .selectinload(TrainingWeek.sessions)
        .selectinload(TrainingSession.lift_slots),
        selectinload(TrainingBlock.weeks)
        .selectinload(TrainingWeek.sessions)
        .selectinload(TrainingSession.prescriptions),
    ).filter(TrainingBlock.athlete_id == athlete_id)
    if exclude_block_id is not None:
        query = query.filter(TrainingBlock.id != exclude_block_id)

    if block_id is not None:
        matches = query.filter(TrainingBlock.id == block_id).all()
    else:
        # Case-fold in Python for deterministic behaviour across SQLite/Postgres
        # collations. Athlete block counts are intentionally small.
        matches = [
            row
            for row in query.all()
            if row.name.strip().casefold() == cleaned_name.casefold()
        ]

    if len(matches) != 1:
        selector = f'id {block_id}' if block_id is not None else f'name "{cleaned_name}"'
        raise ReferenceResolutionError(
            f"Could not uniquely resolve previous block with {selector} for this athlete."
        )
    return matches[0]


def reference_snapshot(block: TrainingBlock) -> dict[str, Any]:
    """Describe reusable coaching architecture without persistence identifiers."""
    weeks = sorted(block.weeks, key=lambda row: (row.position, row.id or 0))
    split: list[dict[str, Any]] = []
    session_notes: list[dict[str, Any]] = []
    frequencies: list[dict[str, int]] = []
    variations: list[dict[str, list[str]]] = []
    prescriptions: list[dict[str, Any]] = []

    for week in weeks:
        sessions = sorted(week.sessions, key=lambda row: (row.position, row.id or 0))
        split.append({
            "week": week.position,
            "sessions": [
                {
                    "position": session.position,
                    "name": session.name,
                    "day_label": session.day_label,
                    "lift_sequence": [slot.lift_family for slot in sorted(
                        session.lift_slots, key=lambda row: (row.position, row.id or 0)
                    )],
                }
                for session in sessions
            ],
        })
        session_notes.append({
            "week": week.position,
            "week_notes": week.notes,
            "sessions": [
                {"position": session.position, "notes": session.notes}
                for session in sessions
            ],
        })
        counts = {family: 0 for family in ("squat", "bench", "deadlift")}
        week_variations = {family: [] for family in counts}
        for session in sessions:
            slot_family = {slot.id: slot.lift_family for slot in session.lift_slots}
            for slot in session.lift_slots:
                counts[slot.lift_family] += 1
            for row in sorted(
                session.prescriptions, key=lambda item: (item.position, item.id or 0)
            ):
                family = slot_family.get(row.lift_slot_id)
                if family and row.exercise_name not in week_variations[family]:
                    week_variations[family].append(row.exercise_name)
                prescriptions.append(
                    _prescription_snapshot(week.position, session.position, family, row)
                )
        frequencies.append({"week": week.position, **counts})
        variations.append({"week": week.position, **week_variations})

    return {
        "schema_version": 1,
        "block_metadata": {"name": block.name, "objective": block.objective},
        "policy": {
            "preserved": list(PRESERVED_ELEMENTS),
            "eligible_to_change": list(ELIGIBLE_TO_CHANGE),
        },
        "split": split,
        "session_notes": session_notes,
        "lift_exposure_frequency": frequencies,
        "lift_variations": variations,
        "prescriptions": prescriptions,
        "progression_shape": _progression_shape(prescriptions),
    }


def proposal_diff(reference: TrainingBlock, proposal: TrainingBlock) -> ProposalDiff:
    """Compare authored proposal to reference; never mutates either block."""
    if reference.athlete_id != proposal.athlete_id:
        raise ReferenceIsolationError("Reference and proposal must belong to the same athlete.")
    reference_value = reference_snapshot(reference)
    proposal_value = reference_snapshot(proposal)
    changes: list[ProposalChange] = []
    for section in (
        "block_metadata",
        "split",
        "session_notes",
        "lift_exposure_frequency",
        "lift_variations",
        "prescriptions",
        "progression_shape",
    ):
        _collect_changes(
            reference_value[section], proposal_value[section], section,
            "preserved" if section in PRESERVED_ELEMENTS else "eligible_to_change",
            changes,
        )
    return ProposalDiff(reference.id, proposal.id, tuple(changes))


def _prescription_snapshot(
    week: int, session: int, family: str | None, row: ExercisePrescription
) -> dict[str, Any]:
    return {
        "week": week, "session": session, "position": row.position,
        "lift_family": family, "exercise": row.exercise_name,
        "slot_role": row.slot_role, "type": row.prescription_type,
        "sets": row.sets, "reps": row.reps, "reps_min": row.reps_min,
        "reps_max": row.reps_max, "percentage": row.percentage, "rpe": row.rpe,
        "rpe_min": row.rpe_min, "rpe_max": row.rpe_max, "rpe_cap": row.rpe_cap,
        "load_kg": row.load_kg, "load_cap_kg": row.load_cap_kg,
        "target_reps": row.target_reps, "target_rpe": row.target_rpe,
        "target_load_kg": row.target_load_kg, "amrap": row.amrap,
        "tempo": row.tempo, "rest_seconds": row.rest_seconds,
    }


def _progression_shape(prescriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe week-to-week direction without freezing absolute target values."""
    numeric_fields = (
        "sets", "reps_min", "reps_max", "percentage", "rpe", "rpe_min",
        "rpe_max", "rpe_cap", "load_kg", "load_cap_kg", "target_reps",
        "target_rpe", "target_load_kg",
    )
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in prescriptions:
        key = (
            row["session"], row["position"], row["lift_family"],
            row["exercise"], row["slot_role"],
        )
        grouped.setdefault(key, []).append(row)
    result = []
    for key, rows in sorted(
        grouped.items(), key=lambda item: tuple(str(value) for value in item[0])
    ):
        ordered = sorted(rows, key=lambda value: value["week"])
        result.append({
            "session": key[0],
            "position": key[1],
            "lift_family": key[2],
            "exercise": key[3],
            "slot_role": key[4],
            "prescription_sequence": [
                {"week": row["week"], "type": row["type"], "reps": row["reps"],
                 "amrap": row["amrap"]}
                for row in ordered
            ],
            "target_directions": {
                field: _directions([row[field] for row in ordered])
                for field in numeric_fields
            },
        })
    return result


def _directions(values: list[Any]) -> list[str]:
    directions = ["baseline"]
    for previous, current in zip(values, values[1:]):
        if previous is None or current is None:
            directions.append("unspecified" if previous == current else "changed")
        elif current > previous:
            directions.append("increase")
        elif current < previous:
            directions.append("decrease")
        else:
            directions.append("same")
    return directions


def _collect_changes(
    before: Any, after: Any, path: str, policy: str, changes: list[ProposalChange]
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            _collect_changes(
                before.get(key), after.get(key), f"{path}.{key}", policy, changes
            )
        return
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            left = before[index] if index < len(before) else None
            right = after[index] if index < len(after) else None
            _collect_changes(left, right, f"{path}[{index}]", policy, changes)
        return
    if before != after:
        changes.append(ProposalChange(path, before, after, policy))
