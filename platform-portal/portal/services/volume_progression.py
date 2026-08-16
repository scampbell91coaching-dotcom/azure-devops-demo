from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence


LIFT_FAMILIES = ("squat", "bench", "deadlift")


@dataclass(frozen=True)
class ReferenceVolume:
    """Average weekly work from a coach-authored reference block."""

    sbd_sets: Mapping[str, int]
    assistance_fatigue_budget: int = 0
    label: str = "reference block"


@dataclass(frozen=True)
class WeeklyVolumeEnvelope:
    week: int
    phase: str
    target_rpe: float
    sbd_sets: dict[str, int]
    sbd_range: dict[str, tuple[int, int]]
    assistance_fatigue_budget: int
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class VolumeProgressionProposal:
    block_type: str
    weeks: tuple[WeeklyVolumeEnvelope, ...]
    explanation: tuple[str, ...]
    overrides_applied: tuple[str, ...]


class VolumeProgressionService:
    """Deterministic, read-only weekly volume proposal.

    S/B/D work is expressed as sets per lift family. Assistance remains a separate
    fatigue-unit budget so adding accessories cannot silently displace exposures.
    """

    _ALIASES = {
        "hypertrophy": "accumulation",
        "development": "accumulation",
        "offseason": "accumulation",
        "peaking": "peak",
    }
    _SETS_PER_EXPOSURE = {
        "accumulation": 4,
        "strength": 3,
        "peak": 3,
        "taper": 1,
    }
    _ASSISTANCE_PER_DAY = {
        "accumulation": 7,
        "strength": 5,
        "peak": 3,
        "taper": 1,
    }

    def propose(
        self,
        *,
        block_type: str,
        duration: int,
        rpe_curve: Sequence[float],
        training_days: int,
        frequencies: Mapping[str, int],
        meet_date: date | None = None,
        constraints: Sequence[str] = (),
        overrides: Sequence[Mapping[str, Any]] = (),
        reference: ReferenceVolume | None = None,
    ) -> VolumeProgressionProposal:
        phase = self._ALIASES.get(block_type, block_type)
        if phase not in self._SETS_PER_EXPOSURE:
            raise ValueError(f"Unsupported block type: {block_type}")
        if duration < 1 or len(rpe_curve) != duration:
            raise ValueError("RPE curve must contain exactly one value per week.")
        if training_days < 1:
            raise ValueError("Training days must be positive.")
        clean_frequencies = self._frequencies(frequencies, training_days)
        clean_rpe = tuple(self._rpe(value) for value in rpe_curve)
        multiplier, fixed_sets, assistance_override, rpe_cap, applied = self._overrides(overrides)

        baseline = {
            family: clean_frequencies[family] * self._SETS_PER_EXPOSURE[phase]
            for family in LIFT_FAMILIES
        }
        explanation = [
            f"{phase.title()} starts from {self._SETS_PER_EXPOSURE[phase]} work sets per exposure across {training_days} training days.",
            "Squat, bench, and deadlift targets are independent of the assistance fatigue budget.",
        ]
        if reference is not None:
            for family in LIFT_FAMILIES:
                value = reference.sbd_sets.get(family)
                if isinstance(value, int) and not isinstance(value, bool) and value >= clean_frequencies[family]:
                    baseline[family] = value
            explanation.append(
                f"Available weekly S/B/D baselines were taken from {reference.label}; phase and RPE adjustments still apply."
            )
        if constraints:
            explanation.append(
                f"{len(constraints)} active athlete constraint flag(s) reduce the upper envelope for coach review; no diagnosis was inferred."
            )
        if meet_date is not None:
            explanation.append(
                f"Meet context ({meet_date.isoformat()}) makes the final peak week a fatigue-reducing taper."
            )

        weeks = []
        previous_rpe = clean_rpe[0]
        for index, target_rpe in enumerate(clean_rpe, start=1):
            if rpe_cap is not None:
                target_rpe = min(target_rpe, rpe_cap)
            week_phase = "taper" if self._is_taper(phase, index, duration, meet_date) else phase
            trajectory = self._trajectory(week_phase, index, duration)
            # Higher exertion consumes recovery: it never earns extra volume.
            rpe_factor = 1.0 if target_rpe <= 7.0 else 0.92 if target_rpe <= 8.0 else 0.82
            if index > 1 and target_rpe > previous_rpe:
                rpe_factor = min(rpe_factor, 0.95)
            phase_cap = self._SETS_PER_EXPOSURE[week_phase]
            targets = {}
            ranges = {}
            for family in LIFT_FAMILIES:
                minimum = clean_frequencies[family]
                raw = baseline[family] * trajectory * rpe_factor * multiplier
                if week_phase in {"peak", "taper"}:
                    raw = min(raw, minimum * phase_cap)
                target = max(minimum, round(raw)) if minimum else 0
                if family in fixed_sets:
                    target = max(minimum, fixed_sets[family]) if minimum else 0
                targets[family] = target
                spread = 0 if week_phase == "taper" else max(1, round(target * 0.1))
                upper = target + spread
                if constraints:
                    upper = target
                ranges[family] = (max(minimum, target - spread), upper)
            assistance = round(
                training_days * self._ASSISTANCE_PER_DAY[week_phase] * trajectory * rpe_factor
            )
            if reference is not None and reference.assistance_fatigue_budget:
                assistance = min(assistance, reference.assistance_fatigue_budget)
            if assistance_override is not None:
                assistance = assistance_override
            week_reasons = [
                f"{week_phase.title()} trajectory factor {trajectory:.2f}; RPE {target_rpe:g} recovery factor {rpe_factor:.2f}."
            ]
            if week_phase == "taper":
                week_reasons.append("Taper caps S/B/D at one set per exposure and sharply reduces assistance fatigue.")
            weeks.append(
                WeeklyVolumeEnvelope(
                    week=index,
                    phase=week_phase,
                    target_rpe=target_rpe,
                    sbd_sets=targets,
                    sbd_range=ranges,
                    assistance_fatigue_budget=max(0, assistance),
                    explanation=tuple(week_reasons),
                )
            )
            previous_rpe = target_rpe
        if applied:
            explanation.append("Explicit coach volume overrides were applied after the deterministic phase calculation.")
        return VolumeProgressionProposal(phase, tuple(weeks), tuple(explanation), applied)

    @staticmethod
    def _rpe(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 10:
            raise ValueError("Target RPE must be between 1 and 10.")
        return float(value)

    @staticmethod
    def _frequencies(values: Mapping[str, int], training_days: int) -> dict[str, int]:
        result = {}
        for family in LIFT_FAMILIES:
            value = values.get(family, 0)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= training_days:
                raise ValueError(f"Invalid {family} frequency.")
            result[family] = value
        return result

    @staticmethod
    def _trajectory(phase: str, week: int, duration: int) -> float:
        progress = 0.0 if duration == 1 else (week - 1) / (duration - 1)
        if phase == "accumulation":
            return 0.9 + (0.2 * progress)
        if phase == "strength":
            return 1.0 - (0.1 * progress)
        if phase == "peak":
            return 1.0 - (0.4 * progress)
        return 0.4

    @staticmethod
    def _is_taper(phase: str, week: int, duration: int, meet_date: date | None) -> bool:
        return phase == "taper" or (phase == "peak" and meet_date is not None and week == duration)

    @staticmethod
    def _overrides(overrides: Sequence[Mapping[str, Any]]) -> tuple[float, dict[str, int], int | None, float | None, tuple[str, ...]]:
        multiplier = 1.0
        fixed: dict[str, int] = {}
        assistance = None
        rpe_cap = None
        applied = []
        for item in overrides:
            payload = item.get("override") if isinstance(item.get("override"), dict) else item
            reason = str(item.get("reason") or "coach-authored override")
            value = payload.get("volume_multiplier")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0.5 <= value <= 1.5:
                multiplier = float(value)
                applied.append(f"Volume multiplier {value:g}: {reason}")
            values = payload.get("weekly_sbd_sets")
            if isinstance(values, dict):
                for family in LIFT_FAMILIES:
                    value = values.get(family)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        fixed[family] = value
                        applied.append(f"{family.title()} set target {value}: {reason}")
            value = payload.get("assistance_fatigue_budget")
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                assistance = value
                applied.append(f"Assistance fatigue budget {value}: {reason}")
            value = payload.get("rpe_cap")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 5 <= value <= 10:
                rpe_cap = float(value)
                applied.append(f"RPE cap {value:g}: {reason}")
        return multiplier, fixed, assistance, rpe_cap, tuple(applied)
