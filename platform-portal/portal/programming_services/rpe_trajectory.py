"""Deterministic, block-aware RPE planning before exercise generation.

The service deliberately has no database or Flask dependencies.  Callers can
persist the returned curve (and any override audit data) as part of their own
programme proposal/revision workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


class BlockType(str, Enum):
    ACCUMULATION = "accumulation"
    STRENGTH = "strength"
    PEAK = "peak"
    TAPER = "taper"
    REBUILD_REHAB = "rebuild/rehab"
    CUSTOM = "custom"


class IntensityPattern(str, Enum):
    RISE = "rise"
    HOLD = "hold"
    WAVE = "wave"
    TAPER = "taper"


@dataclass(frozen=True)
class TrajectoryPolicy:
    """Coach-configurable policy, rather than universal programme constants."""

    minimum_rpe: float = 4.0
    normal_maximum_rpe: float = 9.0
    rebuild_maximum_rpe: float = 8.0
    conservative_start_gap: float = 1.5
    rebuild_start_gap: float = 1.0
    envelope_half_width: float = 0.5
    wave_drop: float = 0.5
    taper_drop: float = 2.0


@dataclass(frozen=True)
class CoachRpeOverride:
    week: int
    target_rpe: float
    coach_id: str
    reason: str
    minimum_rpe: float | None = None
    maximum_rpe: float | None = None


@dataclass(frozen=True)
class AppliedRpeOverride:
    coach_id: str
    reason: str
    requested_target_rpe: float


@dataclass(frozen=True)
class WeeklyRpeEnvelope:
    week: int
    minimum_rpe: float
    target_rpe: float
    maximum_rpe: float
    phase: str
    explanation: str
    override: AppliedRpeOverride | None = None


@dataclass(frozen=True)
class RpeTrajectoryRequest:
    block_type: BlockType
    block_length: int
    target_rpe: float
    target_week: int | None = None
    pattern: IntensityPattern | None = None
    meet_context: bool = False
    overrides: tuple[CoachRpeOverride, ...] = ()


_DEFAULT_PATTERNS = {
    BlockType.ACCUMULATION: IntensityPattern.RISE,
    BlockType.STRENGTH: IntensityPattern.WAVE,
    BlockType.PEAK: IntensityPattern.RISE,
    BlockType.TAPER: IntensityPattern.TAPER,
    BlockType.REBUILD_REHAB: IntensityPattern.HOLD,
}


def build_rpe_trajectory(
    request: RpeTrajectoryRequest,
    *,
    policy: TrajectoryPolicy | None = None,
) -> tuple[WeeklyRpeEnvelope, ...]:
    """Return an explainable RPE envelope for every week in a block."""

    policy = policy or TrajectoryPolicy()
    _validate_request(request, policy)
    target_week = request.target_week
    if target_week is None:
        target_week = 1 if request.block_type is BlockType.TAPER else request.block_length
    pattern = request.pattern or _DEFAULT_PATTERNS.get(request.block_type)
    if pattern is None:
        raise ValueError("custom blocks require an explicit intensity pattern")

    normal_cap = (
        policy.rebuild_maximum_rpe
        if request.block_type is BlockType.REBUILD_REHAB
        else policy.normal_maximum_rpe
    )
    guarded_target = min(request.target_rpe, normal_cap)
    start_gap = (
        policy.rebuild_start_gap
        if request.block_type is BlockType.REBUILD_REHAB
        else policy.conservative_start_gap
    )
    start = max(policy.minimum_rpe, guarded_target - start_gap)
    overrides = {item.week: item for item in request.overrides}
    result: list[WeeklyRpeEnvelope] = []

    for week in range(1, request.block_length + 1):
        target, phase, explanation = _planned_week(
            week=week,
            target_week=target_week,
            block_length=request.block_length,
            start=start,
            target=guarded_target,
            pattern=pattern,
            meet_context=request.meet_context,
            policy=policy,
        )
        target = _half_step(target)
        low = _half_step(max(policy.minimum_rpe, target - policy.envelope_half_width))
        high = _half_step(min(normal_cap, target + policy.envelope_half_width))
        applied = None

        override = overrides.get(week)
        if override is not None:
            target = _half_step(override.target_rpe)
            low = _half_step(
                override.minimum_rpe
                if override.minimum_rpe is not None
                else max(1.0, target - policy.envelope_half_width)
            )
            high = _half_step(
                override.maximum_rpe
                if override.maximum_rpe is not None
                else min(10.0, target + policy.envelope_half_width)
            )
            if not low <= target <= high:
                raise ValueError(f"override for week {week} must contain its target")
            phase = "coach_override"
            explanation = f"Coach override: {override.reason}"
            applied = AppliedRpeOverride(
                coach_id=override.coach_id,
                reason=override.reason,
                requested_target_rpe=override.target_rpe,
            )

        result.append(
            WeeklyRpeEnvelope(
                week=week,
                minimum_rpe=low,
                target_rpe=target,
                maximum_rpe=high,
                phase=phase,
                explanation=explanation,
                override=applied,
            )
        )

    return tuple(result)


def _planned_week(
    *,
    week: int,
    target_week: int,
    block_length: int,
    start: float,
    target: float,
    pattern: IntensityPattern,
    meet_context: bool,
    policy: TrajectoryPolicy,
) -> tuple[float, str, str]:
    if week > target_week and (meet_context or pattern is IntensityPattern.TAPER):
        remaining = max(1, block_length - target_week)
        progress = (week - target_week) / remaining
        value = target - policy.taper_drop * progress
        return value, "fatigue_reduction", "RPE falls after the target week to reduce fatigue"

    if week > target_week:
        return target, "hold", "RPE holds after the configured target week"

    progress = 1.0 if target_week == 1 else (week - 1) / (target_week - 1)
    rising = start + (target - start) * progress
    if pattern is IntensityPattern.HOLD:
        return start, "hold", "RPE holds at the conservative block entry level"
    if pattern is IntensityPattern.TAPER and target_week == 1:
        return target, "target", "Taper begins from the configured target RPE"
    if pattern is IntensityPattern.WAVE and week < target_week and week % 2 == 0:
        return rising - policy.wave_drop, "wave_down", "Planned down-wave limits accumulated fatigue"
    phase = "target" if week == target_week else "build"
    return rising, phase, "RPE progresses toward the configured target week"


def _validate_request(request: RpeTrajectoryRequest, policy: TrajectoryPolicy) -> None:
    if request.block_length < 1:
        raise ValueError("block_length must be at least one week")
    target_week = request.target_week
    if target_week is not None and not 1 <= target_week <= request.block_length:
        raise ValueError("target_week must fall within the block")
    if not 1.0 <= request.target_rpe <= 10.0:
        raise ValueError("target_rpe must be between 1 and 10")
    if not 1.0 <= policy.minimum_rpe <= policy.normal_maximum_rpe <= 10.0:
        raise ValueError("policy RPE bounds must be ordered within the RPE scale")
    if not policy.minimum_rpe <= policy.rebuild_maximum_rpe <= 10.0:
        raise ValueError("rebuild policy bounds must be ordered within the RPE scale")
    if any(
        value < 0
        for value in (
            policy.conservative_start_gap,
            policy.rebuild_start_gap,
            policy.envelope_half_width,
            policy.wave_drop,
            policy.taper_drop,
        )
    ):
        raise ValueError("policy gaps and drops cannot be negative")
    seen: set[int] = set()
    for override in request.overrides:
        if override.week in seen:
            raise ValueError(f"only one override is allowed for week {override.week}")
        seen.add(override.week)
        if not 1 <= override.week <= request.block_length:
            raise ValueError("override week must fall within the block")
        if not override.coach_id.strip() or not override.reason.strip():
            raise ValueError("coach overrides require coach_id and reason")
        values = (override.target_rpe, override.minimum_rpe, override.maximum_rpe)
        if any(value is not None and not 1.0 <= value <= 10.0 for value in values):
            raise ValueError("override RPE values must be between 1 and 10")


def _half_step(value: float) -> float:
    return float((Decimal(str(value)) * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2)
