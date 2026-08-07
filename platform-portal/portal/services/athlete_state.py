"""Explainable athlete-state calculation and recording services."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from ..extensions import db
from ..models.athlete import Athlete
from ..models.athlete_state import AthleteStateFact, AthleteStateSignal
from ..models.checkins import WeeklyCheckin
from ..models.programming import TrainingSessionLog, TrainingSetResult

CALCULATION_VERSION = "athlete-state-v1"
FACT_TYPES = {
    "training_start_date", "experience_level", "competition_date",
    "training_days_per_week", "squat_exposures_per_week",
    "bench_exposures_per_week", "deadlift_exposures_per_week",
}
FREQUENCY_FACTS = {
    "training_days_per_week", "squat_exposures_per_week",
    "bench_exposures_per_week", "deadlift_exposures_per_week",
}


@dataclass(frozen=True)
class SignalDraft:
    signal_type: str
    value: object
    source_refs: tuple[str, ...]
    explanation: str
    window_start: date | None = None
    window_end: date | None = None


def record_fact(*, athlete_id: int, fact_type: str, value: object,
                source_type: str, recorded_by: str | None = None,
                source_ref: str | None = None, effective_on: date | None = None,
                supersedes: AthleteStateFact | None = None) -> AthleteStateFact:
    """Record a sourced fact revision; this deliberately never guesses values."""
    if fact_type not in FACT_TYPES:
        raise ValueError(f"Unsupported athlete-state fact type: {fact_type}")
    if source_type not in {"athlete", "coach", "import", "legacy"}:
        raise ValueError("Invalid fact source type")
    if fact_type in FREQUENCY_FACTS and (
        isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 14
    ):
        raise ValueError("Weekly frequency must be an integer from 0 to 14")
    if fact_type in {"training_start_date", "competition_date"}:
        if not isinstance(value, str):
            raise ValueError("Date facts must use ISO YYYY-MM-DD strings")
        date.fromisoformat(value)
    if supersedes is not None and (
        supersedes.athlete_id != athlete_id or supersedes.fact_type != fact_type
    ):
        raise ValueError("A fact can only supersede the same athlete and fact type")
    fact = AthleteStateFact(
        athlete_id=athlete_id, fact_type=fact_type, value_json=value,
        source_type=source_type, source_ref=source_ref, recorded_by=recorded_by,
        effective_on=effective_on, supersedes=supersedes,
    )
    db.session.add(fact)
    return fact


def latest_facts(athlete_id: int) -> dict[str, AthleteStateFact]:
    facts = AthleteStateFact.query.filter_by(athlete_id=athlete_id).order_by(
        AthleteStateFact.recorded_at.asc(), AthleteStateFact.id.asc()
    ).all()
    superseded = {item.supersedes_id for item in facts if item.supersedes_id}
    return {item.fact_type: item for item in facts if item.id not in superseded}


def calculate_signals(athlete: Athlete, *, as_of: date | None = None,
                      window_days: int = 28) -> list[SignalDraft]:
    """Calculate only signals supported by stored inputs, with input references."""
    as_of = as_of or date.today()
    start = as_of - timedelta(days=window_days - 1)
    signals: list[SignalDraft] = []
    facts = latest_facts(athlete.id)

    training_start = _date_fact(facts.get("training_start_date"))
    if training_start is not None and training_start <= as_of:
        signals.append(SignalDraft(
            "training_age_days", (as_of - training_start).days,
            (f"athlete_state_fact:{facts['training_start_date'].id}",),
            f"Days from recorded training start {training_start.isoformat()} to {as_of.isoformat()}.",
        ))

    competition, reference = _competition_date(athlete, facts)
    if competition is not None:
        signals.append(SignalDraft(
            "days_to_competition", (competition - as_of).days, (reference,),
            f"Calendar days from {as_of.isoformat()} to recorded competition date {competition.isoformat()}.",
        ))

    checkin = WeeklyCheckin.query.filter(
        WeeklyCheckin.athlete_id == athlete.id,
        WeeklyCheckin.week_ending <= as_of,
    ).order_by(WeeklyCheckin.week_ending.desc(), WeeklyCheckin.id.desc()).first()
    if checkin is not None:
        for signal_type, field in (
            ("reported_training_adherence", "training_adherence"),
            ("reported_fatigue", "fatigue"), ("reported_recovery", "recovery"),
        ):
            value = getattr(checkin, field)
            if value is not None:
                signals.append(SignalDraft(
                    signal_type, value, (f"weekly_checkin:{checkin.id}:{field}",),
                    f"Most recent recorded weekly check-in value ({checkin.week_ending.isoformat()}); no imputation.",
                ))

    logs = TrainingSessionLog.query.filter(
        TrainingSessionLog.athlete_id == athlete.id,
        TrainingSessionLog.started_at >= datetime.combine(start, datetime.min.time()),
        TrainingSessionLog.started_at < datetime.combine(as_of + timedelta(days=1), datetime.min.time()),
    ).all()
    if logs:
        completed = sum(item.status == "completed" for item in logs)
        signals.append(SignalDraft(
            "logged_session_completion_rate", round(completed / len(logs), 4),
            tuple(f"training_session_log:{item.id}" for item in logs),
            f"{completed} completed of {len(logs)} started/logged sessions; unlogged assignments are not counted.", start, as_of,
        ))

    rows = (TrainingSetResult.query.join(TrainingSessionLog)
            .filter(TrainingSessionLog.athlete_id == athlete.id,
                    TrainingSessionLog.started_at >= datetime.combine(start, datetime.min.time()),
                    TrainingSessionLog.started_at < datetime.combine(as_of + timedelta(days=1), datetime.min.time()))
            .all())
    decided = [row for row in rows if row.completed or row.skipped]
    if decided:
        signals.append(SignalDraft(
            "set_completion_rate", round(sum(row.completed for row in decided) / len(decided), 4),
            tuple(f"training_set_result:{row.id}" for row in decided),
            f"Completed sets divided by {len(decided)} sets marked completed or skipped.", start, as_of,
        ))
    rpe_rows = [row for row in rows if row.completed and row.prescribed_rpe is not None and row.actual_rpe is not None]
    if rpe_rows:
        within = sum(abs(row.actual_rpe - row.prescribed_rpe) <= 0.5 for row in rpe_rows)
        signals.append(SignalDraft(
            "rpe_adherence_rate", round(within / len(rpe_rows), 4),
            tuple(f"training_set_result:{row.id}:actual_rpe,prescribed_rpe" for row in rpe_rows),
            f"{within} of {len(rpe_rows)} completed sets were within ±0.5 RPE of prescription.", start, as_of,
        ))
    return signals


def persist_signal_snapshot(athlete: Athlete, *, as_of: date | None = None) -> list[AthleteStateSignal]:
    snapshot_id = str(uuid4())
    calculated_at = datetime.now(UTC)
    records = [AthleteStateSignal(
        athlete_id=athlete.id, snapshot_id=snapshot_id, signal_type=item.signal_type,
        value_json=item.value, window_start=item.window_start, window_end=item.window_end,
        calculation_version=CALCULATION_VERSION, source_refs_json=list(item.source_refs),
        explanation=item.explanation, calculated_at=calculated_at,
    ) for item in calculate_signals(athlete, as_of=as_of)]
    db.session.add_all(records)
    return records


def _date_fact(fact: AthleteStateFact | None) -> date | None:
    if fact is None or not isinstance(fact.value_json, str):
        return None
    try:
        return date.fromisoformat(fact.value_json)
    except ValueError:
        return None


def _competition_date(athlete: Athlete, facts: dict[str, AthleteStateFact]) -> tuple[date | None, str]:
    fact = facts.get("competition_date")
    parsed = _date_fact(fact)
    if parsed is not None:
        return parsed, f"athlete_state_fact:{fact.id}"
    # Reuse a legacy value only when it is already an unambiguous ISO date.
    try:
        return date.fromisoformat(athlete.next_competition or ""), f"athlete:{athlete.id}:next_competition"
    except ValueError:
        return None, ""
