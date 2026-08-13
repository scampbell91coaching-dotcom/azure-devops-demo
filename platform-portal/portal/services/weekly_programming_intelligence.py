from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ..models.athlete_state import (
    AthleteStateOverride,
)
from ..models.exercise_library import Exercise
from ..models.programming import TrainingBlock
from .athlete_state import calculate_signals, latest_facts
from .programming_athlete_state import aggregate_programming_athlete_state
from .volume_progression import (
    ReferenceVolume,
    VolumeProgressionProposal,
    VolumeProgressionService,
)


class FactoryInputs(Protocol):
    athlete_id: int
    week_count: int
    training_days: int
    squat_frequency: int
    bench_frequency: int
    deadlift_frequency: int
    goal: str
    meet_date: Any


@dataclass(frozen=True)
class AthleteProgrammingContext:
    athlete_id: int
    bodyweight_kg: float | None
    weight_class: str | None
    next_competition: str | None
    existing_blocks: int
    state_facts: dict[str, Any]
    state_signals: dict[str, Any]
    active_constraints: tuple[str, ...]
    technical_observations: tuple[str, ...]
    active_overrides: tuple[dict[str, Any], ...]
    missing: tuple[str, ...]
    programming_state: dict[str, Any]


@dataclass(frozen=True)
class WeeklyIntelligencePreview:
    weekly_structure: tuple[dict[str, Any], ...]
    exposures: dict[str, int]
    reasoning: tuple[str, ...]
    fatigue: dict[str, Any]
    volume: VolumeProgressionProposal
    constraints: tuple[str, ...]
    data: AthleteProgrammingContext


def _reference_volume(athlete_id: int) -> ReferenceVolume | None:
    block = (
        TrainingBlock.query.filter_by(athlete_id=athlete_id)
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    if block is None or not block.weeks:
        return None
    totals = {family: 0 for family in ("squat", "bench", "deadlift")}
    assistance_fatigue = 0
    for week in block.weeks:
        for session in week.sessions:
            for item in session.prescriptions:
                sets = item.sets or 0
                if item.lift_slot is not None:
                    totals[item.lift_slot.lift_family] += sets
                else:
                    assistance_fatigue += max(
                        1, min(5, item.exercise.fatigue_rating if item.exercise else 3)
                    )
    count = len(block.weeks)
    return ReferenceVolume(
        sbd_sets={family: round(value / count) for family, value in totals.items()},
        assistance_fatigue_budget=round(assistance_fatigue / count),
        label=block.name,
    )


def _rpe_curve(factory: FactoryInputs) -> tuple[float, ...]:
    bounds = {
        "hypertrophy": (6.0, 7.5),
        "development": (6.0, 8.0),
        "strength": (6.5, 8.5),
        "peaking": (7.0, 9.0),
        "offseason": (6.0, 7.5),
    }
    start, end = bounds[factory.goal]
    if factory.week_count == 1:
        return (start,)
    values = []
    for week in range(1, factory.week_count + 1):
        progress = (week - 1) / (factory.week_count - 1)
        value = start + ((end - start) * progress)
        if factory.goal != "peaking" and week == factory.week_count:
            value = max(start, value - 1.0)
        values.append(round(value * 2) / 2)
    return tuple(values)


def _requested_split_baseline(
    factory: FactoryInputs, days: Sequence[dict[str, Any]]
) -> ReferenceVolume:
    totals = {family: 0 for family in ("squat", "bench", "deadlift")}
    family_by_code = {"S": "squat", "B": "bench", "D": "deadlift"}
    for day in days:
        for position, code in enumerate(day["day_type"], start=1):
            sets = 3
            if factory.goal == "strength" and position == 1:
                sets = 4
            elif factory.goal == "peaking" and position == 1:
                sets = 1
            totals[family_by_code[code]] += sets
    return ReferenceVolume(totals, label="the requested split's V7.10 baseline")


def map_athlete_programming_context(athlete: Any) -> AthleteProgrammingContext:
    """Consume Athlete State V6 without persisting or inventing athlete data."""
    blocks = TrainingBlock.query.filter_by(athlete_id=athlete.id).count()
    facts = {name: fact.value_json for name, fact in latest_facts(athlete.id).items()}
    signals = {
        signal.signal_type: signal.value for signal in calculate_signals(athlete)
    }
    programming_state = aggregate_programming_athlete_state(athlete)
    active_constraints = tuple(
        item["label"] for item in programming_state["hard_constraints"]
    )
    technical_observations = tuple(
        item["label"] for item in programming_state["soft_signals"]
        if item["kind"] == "technical_observation"
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    active_overrides = tuple(
        {
            "target_type": item.target_type,
            "target_ref": item.target_ref,
            "override": item.override_json,
            "reason": item.reason,
            "recorded_by": item.recorded_by,
        }
        for item in AthleteStateOverride.query.filter(
            AthleteStateOverride.athlete_id == athlete.id,
            AthleteStateOverride.target_type != "programming_proposal",
            AthleteStateOverride.revoked_at.is_(None),
            (
                AthleteStateOverride.expires_at.is_(None)
                | (AthleteStateOverride.expires_at > now)
            ),
        ).order_by(
            AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc()
        )
    )
    missing = []
    if athlete.bodyweight_kg is None:
        missing.append("bodyweight")
    if not athlete.weight_class:
        missing.append("weight class")
    if "competition_date" not in facts and not athlete.next_competition:
        missing.append("competition date")
    if "rpe_adherence_rate" not in signals:
        missing.append("RPE adherence signal")
    return AthleteProgrammingContext(
        athlete_id=athlete.id,
        bodyweight_kg=athlete.bodyweight_kg,
        weight_class=athlete.weight_class,
        next_competition=athlete.next_competition,
        existing_blocks=blocks,
        state_facts=facts,
        state_signals=signals,
        active_constraints=active_constraints,
        technical_observations=technical_observations,
        active_overrides=active_overrides,
        missing=tuple(missing),
        programming_state=programming_state,
    )


def _exercise_taxonomy(days: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    names = {name for day in days for name in day["exercises"][: day["main_count"]]}
    rows = Exercise.query.filter(
        Exercise.name.in_(names), Exercise.active.is_(True)
    ).all()
    return {
        row.name: {
            "lift_family": row.lift_family,
            "movement_pattern": row.movement_pattern,
            "specificity": row.specificity,
            "technical_purposes": row.technical_purposes,
            "equipment_options": row.equipment_options,
            "constraint_tags": row.constraint_tags,
            "variation_of": row.variation_of,
            "swap_group": row.swap_group,
        }
        for row in rows
    }


class WeeklyProgrammingIntelligence:
    """Read-only boundary between Block Factory and programming intelligence."""

    def preview(
        self,
        factory: FactoryInputs,
        athlete: Any,
        days: Sequence[dict[str, Any]],
    ) -> WeeklyIntelligencePreview:
        context = map_athlete_programming_context(athlete)
        taxonomy = _exercise_taxonomy(days)
        structure = tuple(
            {
                "day": day["day"],
                "day_type": day["day_type"],
                "exposures": tuple(day["exercises"][: day["main_count"]]),
                "exposure_taxonomy": tuple(
                    taxonomy.get(name) for name in day["exercises"][: day["main_count"]]
                ),
                "assistance": tuple(item["name"] for item in day["accessories"]),
            }
            for day in days
        )
        if any(not day["exposures"] for day in structure):
            raise ValueError("Every training day must contain a powerlifting exposure.")

        constraints = [
            "Every day is organised around squat, bench, or deadlift exposure.",
            "Assistance is optional, subordinate, and never creates another day.",
            "Coach edits override this proposal; accepting is the only write action.",
            "Use target RPE to adjust load rather than forcing a predetermined load.",
        ]
        if context.missing:
            constraints.append(
                "Incomplete data: "
                + ", ".join(context.missing)
                + ". No assumptions were substituted."
            )
        if context.active_constraints:
            constraints.append(
                "Reported training constraints for coach review: "
                + ", ".join(context.active_constraints)
                + ". No diagnosis or exercise-suitability inference was made."
            )
        if context.technical_observations:
            constraints.append(
                "Active coach technical observations for review: "
                + "; ".join(context.technical_observations)
                + ". No diagnosis or automatic exercise change was made."
            )
        if context.active_overrides:
            constraints.append(
                "Active coach overrides are authoritative: "
                + "; ".join(
                    f"{item['target_type']} {item['target_ref']} — {item['reason']}"
                    for item in context.active_overrides
                )
                + ". The generator did not replace them."
            )
        uncatalogued = sorted(
            {
                name
                for day in structure
                for name, metadata in zip(day["exposures"], day["exposure_taxonomy"])
                if metadata is None
            }
        )
        if uncatalogued:
            constraints.append(
                "Exercise Library metadata is incomplete for: "
                + ", ".join(uncatalogued)
                + ". The proposal kept the established exposure names."
            )

        raw_adherence = context.state_signals.get("rpe_adherence_rate")
        adherence = (
            max(0.0, min(1.0, float(raw_adherence)))
            if isinstance(raw_adherence, (int, float))
            and not isinstance(raw_adherence, bool)
            else None
        )
        reported_fatigue = context.state_signals.get("reported_fatigue")
        fatigue = {
            "status": "reported" if reported_fatigue is not None else "not reported",
            "detail": (
                f"Latest reported fatigue is {reported_fatigue}."
                if reported_fatigue is not None
                else "No reported fatigue data exists; none was inferred."
            ),
            "rpe_adherence": (
                f"{adherence:.0%} of comparable sets were within ±0.5 RPE."
                if adherence is not None
                else "No RPE-adherence signal exists for the current window."
            ),
        }
        volume = VolumeProgressionService().propose(
            block_type=factory.goal,
            duration=factory.week_count,
            rpe_curve=_rpe_curve(factory),
            training_days=factory.training_days,
            frequencies={
                "squat": factory.squat_frequency,
                "bench": factory.bench_frequency,
                "deadlift": factory.deadlift_frequency,
            },
            meet_date=factory.meet_date,
            constraints=context.active_constraints,
            overrides=context.active_overrides,
            reference=_reference_volume(athlete.id)
            or _requested_split_baseline(factory, days),
        )

        reasoning = [
            "Squat, bench, and deadlift exposures were established before assistance.",
            f"The requested {factory.goal} structure uses {factory.training_days} exposure-led days.",
            f"Coach inputs requested {factory.squat_frequency} squat, {factory.bench_frequency} bench, "
            f"and {factory.deadlift_frequency} deadlift exposures; the summary counts only "
            "taxonomy-confirmed selections.",
        ]
        catalogued = sum(
            metadata is not None
            for day in structure
            for metadata in day["exposure_taxonomy"]
        )
        if catalogued:
            reasoning.append(
                f"Exercise Library V6 taxonomy was available for {catalogued} exposure selections; "
                "swap groups remain read-only metadata."
            )
        if not any(day["assistance"] for day in structure):
            reasoning.append(
                "No assistance was added because none was pinned by the coach."
            )
        else:
            reasoning.append(
                "Only coach-pinned assistance was retained, without a quota."
            )

        return WeeklyIntelligencePreview(
            weekly_structure=structure,
            exposures={
                family: sum(
                    metadata is not None and metadata["lift_family"] == family
                    for day in structure
                    for metadata in day["exposure_taxonomy"]
                )
                for family in ("squat", "bench", "deadlift")
            },
            reasoning=tuple(reasoning),
            fatigue=fatigue,
            volume=volume,
            constraints=tuple(constraints),
            data=context,
        )
