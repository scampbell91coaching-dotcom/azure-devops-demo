"""Deterministic presentation model for generated programming proposals.

This module deliberately formats supplied generation evidence; it does not make
programming decisions or invent a rationale after the fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


EXPLANATION_SCHEMA_VERSION = "proposal-explanation-v1"


@dataclass(frozen=True)
class Provenance:
    id: str
    kind: str
    label: str
    value: Any


@dataclass(frozen=True)
class ExplainedItem:
    id: str
    label: str
    reason_id: str
    reason: str
    provenance_ids: tuple[str, ...]


@dataclass(frozen=True)
class CurvePoint:
    week: int
    value: float


@dataclass(frozen=True)
class ProposalExplanation:
    schema_version: str
    reference_block: ExplainedItem
    kept: tuple[ExplainedItem, ...]
    changed: tuple[ExplainedItem, ...]
    rpe_curve: tuple[CurvePoint, ...]
    volume_curve: tuple[CurvePoint, ...]
    athlete_state_evidence: tuple[Provenance, ...]
    warm_ups: tuple[ExplainedItem, ...]
    assistance: tuple[ExplainedItem, ...]
    coach_overrides: tuple[ExplainedItem, ...]
    warnings: tuple[ExplainedItem, ...]


def _unique_names(days: Sequence[Mapping[str, Any]], key: str) -> tuple[str, ...]:
    names = {
        str(item)
        for day in days
        for item in day.get(key, ())
        if str(item).strip()
    }
    return tuple(sorted(names, key=lambda value: (value.casefold(), value)))


def _item(
    item_id: str,
    label: str,
    reason_id: str,
    reason: str,
    *provenance_ids: str,
) -> ExplainedItem:
    return ExplainedItem(item_id, label, reason_id, reason, tuple(provenance_ids))


class ProposalExplanationService:
    """Build a stable DTO solely from explicit proposal inputs and evidence."""

    def build(
        self,
        *,
        factory: Any,
        weekly_structure: Sequence[Mapping[str, Any]],
        context: Any,
        rpe_values: Sequence[float],
        volume_values: Sequence[float],
        reference_block: Mapping[str, Any] | None = None,
        assistance_reasons: Mapping[str, Sequence[str]] | None = None,
    ) -> ProposalExplanation:
        proposed = _unique_names(weekly_structure, "exposures")
        reference_exercises = tuple(
            sorted(
                {str(value) for value in (reference_block or {}).get("exercises", ())},
                key=lambda value: (value.casefold(), value),
            )
        )
        kept_names = tuple(name for name in proposed if name in reference_exercises)
        added_names = (
            tuple(name for name in proposed if name not in reference_exercises)
            if reference_block
            else ()
        )
        removed_names = tuple(name for name in reference_exercises if name not in proposed)

        if reference_block:
            reference = _item(
                "reference-block",
                f"{reference_block['name']} (block {reference_block['id']})",
                "reference.latest-athlete-block",
                "The latest existing athlete block was used as the presentation comparison.",
                f"training-block:{reference_block['id']}",
            )
        else:
            reference = _item(
                "reference-block",
                "No reference block",
                "reference.none-available",
                "No existing athlete block was available; no continuity claim was made.",
            )

        kept = tuple(
            _item(
                f"kept-exposure:{name}",
                name,
                "diff.exposure-unchanged",
                "This exposure appears in both the reference and proposal.",
                f"training-block:{reference_block['id']}",
                "coach-input:weekly-structure",
            )
            for name in kept_names
        )
        changed = tuple(
            _item(
                f"added-exposure:{name}",
                f"Added {name}",
                "diff.exposure-added",
                "This proposed exposure does not appear in the reference block.",
                "coach-input:weekly-structure",
            )
            for name in added_names
        ) + tuple(
            _item(
                f"removed-exposure:{name}",
                f"Excluded {name}",
                "diff.exposure-removed",
                "This reference exposure does not appear in the proposal.",
                f"training-block:{reference_block['id']}",
            )
            for name in removed_names
        )

        evidence: list[Provenance] = []
        for name, value in sorted(context.state_facts.items()):
            evidence.append(Provenance(f"athlete-state:fact:{name}", "fact", name, value))
        for name, value in sorted(context.state_signals.items()):
            evidence.append(
                Provenance(f"athlete-state:signal:{name}", "signal", name, value)
            )
        for index, value in enumerate(context.active_constraints, start=1):
            evidence.append(
                Provenance(
                    f"athlete-state:constraint:{index}", "constraint", "constraint", value
                )
            )
        for index, value in enumerate(context.technical_observations, start=1):
            evidence.append(
                Provenance(
                    f"athlete-state:technical-observation:{index}",
                    "technical_observation",
                    "technical observation",
                    value,
                )
            )

        assistance_names = _unique_names(weekly_structure, "assistance")
        assistance_reasons = assistance_reasons or {}
        assistance = tuple(
            _item(
                f"assistance:{name}",
                name,
                "assistance.explicit-selection",
                "; ".join(assistance_reasons.get(name, ()))
                or "Included by the deterministic assistance selection recorded in the proposal.",
                "proposal:weekly-structure",
            )
            for name in assistance_names
        )
        if not assistance:
            assistance = (
                _item(
                    "assistance:none",
                    "No assistance suggested",
                    "assistance.none-selected",
                    "No assistance selection is present in the proposal.",
                    "proposal:weekly-structure",
                ),
            )

        overrides = tuple(
            _item(
                f"coach-override:{index}",
                f"{value['target_type']} {value['target_ref']}",
                "override.active-authoritative",
                str(value["reason"]),
                f"coach-override:{index}",
            )
            for index, value in enumerate(context.active_overrides, start=1)
        )
        warnings = tuple(
            _item(
                f"warning:missing:{name}",
                f"Missing {name}",
                "warning.input-missing",
                "No value was available and none was inferred.",
            )
            for name in sorted(context.missing, key=str.casefold)
        )
        if not reference_block:
            warnings += (
                _item(
                    "warning:reference-block-missing",
                    "Exposure diff unavailable",
                    "warning.reference-missing",
                    "No reference block was available, so exposures were not labelled as added or removed.",
                ),
            )

        return ProposalExplanation(
            schema_version=EXPLANATION_SCHEMA_VERSION,
            reference_block=reference,
            kept=kept,
            changed=changed,
            rpe_curve=tuple(
                CurvePoint(week=index, value=float(value))
                for index, value in enumerate(rpe_values, start=1)
            ),
            volume_curve=tuple(
                CurvePoint(week=index, value=float(value))
                for index, value in enumerate(volume_values, start=1)
            ),
            athlete_state_evidence=tuple(evidence),
            warm_ups=(
                _item(
                    "warm-up:none",
                    "No warm-ups suggested",
                    "warmup.outside-generator-scope",
                    "This proposal generator did not evaluate or prescribe warm-ups.",
                ),
            ),
            assistance=assistance,
            coach_overrides=overrides,
            warnings=warnings,
        )
