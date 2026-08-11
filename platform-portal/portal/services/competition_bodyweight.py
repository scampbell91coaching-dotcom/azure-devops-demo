"""Read-only competition and bodyweight planning context.

This module deliberately composes existing Athlete, Meet, and check-in records.
It does not persist a recommendation or interpret a weight-class label as a target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from ..models.checkins import WeeklyCheckin
from ..models.meet_day import Meet, MeetEntry
from ..models.nutrition_checkin import NutritionCheckIn


@dataclass(frozen=True)
class CompetitionReference:
    name: str | None
    competition_date: date | None
    source: str | None
    source_ref: str | None
    days_away: int | None


@dataclass(frozen=True)
class BodyweightObservation:
    recorded_on: date | None
    bodyweight_kg: Decimal
    source: str
    source_ref: str


@dataclass(frozen=True)
class BodyweightPlanningContext:
    athlete_id: int
    competition: CompetitionReference
    weight_class: str | None
    latest: BodyweightObservation | None
    recent: tuple[BodyweightObservation, ...]
    target_bodyweight_kg: Decimal | None
    change_required_kg: Decimal | None
    weeks_available: Decimal | None
    required_change_per_week_kg: Decimal | None
    prompts: tuple[str, ...]


def build_bodyweight_planning_context(
    athlete,
    *,
    as_of: date,
    target_bodyweight_kg: Decimal | float | str | None = None,
    history_limit: int = 8,
) -> BodyweightPlanningContext:
    """Build an explainable planning input without changing any records.

    ``target_bodyweight_kg`` is an explicit, transient coach input. The existing
    free-text ``weight_class`` is displayed but never parsed into a target.
    """
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    target = _positive_decimal(target_bodyweight_kg, "target_bodyweight_kg")
    competition = _competition_reference(athlete, as_of)
    recent = _bodyweight_history(athlete, as_of, history_limit)
    latest = recent[-1] if recent else _athlete_bodyweight(athlete)

    prompts: list[str] = []
    if competition.competition_date is None:
        prompts.append("Confirm a structured competition date.")
    elif competition.days_away is not None and competition.days_away < 0:
        prompts.append("Competition date is in the past; confirm the next competition.")
    if latest is None:
        prompts.append("Record a current bodyweight before planning change.")
    if not athlete.weight_class:
        prompts.append("Confirm the competition weight class.")
    if target is None:
        prompts.append("Set an explicit target bodyweight; weight class is not used as a proxy.")

    change = None
    weeks = None
    weekly = None
    if latest is not None and target is not None:
        change = _kg(target - latest.bodyweight_kg)
    if competition.days_away is not None and competition.days_away > 0:
        weeks = (Decimal(competition.days_away) / Decimal(7)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if change is not None:
            weekly = (change / weeks).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    if change is not None and change != 0:
        prompts.append("Coach review is required before applying a bodyweight change target.")

    return BodyweightPlanningContext(
        athlete_id=athlete.id,
        competition=competition,
        weight_class=athlete.weight_class,
        latest=latest,
        recent=recent,
        target_bodyweight_kg=target,
        change_required_kg=change,
        weeks_available=weeks,
        required_change_per_week_kg=weekly,
        prompts=tuple(prompts),
    )


def _competition_reference(athlete, as_of: date) -> CompetitionReference:
    entry = (
        MeetEntry.query.join(Meet)
        .filter(
            MeetEntry.athlete_id == athlete.id,
            Meet.status.in_(("planned", "active")),
            Meet.meet_date >= as_of,
        )
        .order_by(Meet.meet_date.asc(), Meet.id.asc())
        .first()
    )
    if entry is not None:
        meet = entry.meet
        return CompetitionReference(
            meet.name, meet.meet_date, "meet_entry", f"meet:{meet.id}",
            (meet.meet_date - as_of).days,
        )

    raw = (athlete.next_competition or "").strip()
    try:
        competition_date = date.fromisoformat(raw)
    except ValueError:
        competition_date = None
    return CompetitionReference(
        raw or None,
        competition_date,
        "athlete" if raw else None,
        f"athlete:{athlete.id}:next_competition" if raw else None,
        (competition_date - as_of).days if competition_date else None,
    )


def _bodyweight_history(athlete, as_of: date, limit: int) -> tuple[BodyweightObservation, ...]:
    weekly = WeeklyCheckin.query.filter(
        WeeklyCheckin.athlete_id == athlete.id,
        WeeklyCheckin.week_ending <= as_of,
        WeeklyCheckin.average_bodyweight_kg.isnot(None),
    ).all()
    nutrition = NutritionCheckIn.query.filter(
        NutritionCheckIn.athlete_id == athlete.id,
        NutritionCheckIn.checkin_date <= as_of,
        NutritionCheckIn.bodyweight_kg.isnot(None),
    ).all()
    observations = [
        BodyweightObservation(item.week_ending, _kg(item.average_bodyweight_kg),
                              "weekly_checkin", f"weekly_checkin:{item.id}")
        for item in weekly
    ] + [
        BodyweightObservation(item.checkin_date, _kg(item.bodyweight_kg),
                              "nutrition_checkin", f"nutrition_checkin:{item.id}")
        for item in nutrition
    ]
    observations.sort(key=lambda item: (item.recorded_on, item.source_ref))
    return tuple(observations[-limit:])


def _athlete_bodyweight(athlete) -> BodyweightObservation | None:
    if athlete.bodyweight_kg is None:
        return None
    return BodyweightObservation(
        None, _kg(athlete.bodyweight_kg), "athlete", f"athlete:{athlete.id}:bodyweight"
    )


def _positive_decimal(value, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return _kg(parsed)


def _kg(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
