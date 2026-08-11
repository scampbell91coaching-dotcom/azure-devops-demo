"""Read-only competition and bodyweight planning context.

This module deliberately composes existing Athlete, Meet, and check-in records.
It does not persist a recommendation or interpret a weight-class label as a target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import contains_eager

from ..models.athlete import Athlete
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
    federation: str | None = None
    weight_class: str | None = None
    status: str | None = None


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


@dataclass(frozen=True)
class BodyweightTrend:
    """Dashboard-safe trend facts; no direction is invented from one point."""

    status: str
    change_kg: Decimal | None
    span_days: int | None
    direction: str | None


@dataclass(frozen=True)
class AthleteCompetitionDashboardContext:
    athlete_id: int
    bodyweight: BodyweightPlanningContext
    trend: BodyweightTrend


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
    return _build_context(
        athlete,
        as_of=as_of,
        target_bodyweight_kg=target_bodyweight_kg,
        competition=_competition_reference(athlete, as_of),
        recent=_bodyweight_history(athlete, as_of, history_limit),
    )


def _build_context(
    athlete,
    *,
    as_of: date,
    target_bodyweight_kg,
    competition: CompetitionReference,
    recent: tuple[BodyweightObservation, ...],
) -> BodyweightPlanningContext:
    target = _positive_decimal(target_bodyweight_kg, "target_bodyweight_kg")
    latest = recent[-1] if recent else _athlete_bodyweight(athlete)
    weight_class = competition.weight_class or athlete.weight_class

    prompts: list[str] = []
    if competition.competition_date is None:
        prompts.append("Confirm a structured competition date.")
    elif competition.days_away is not None and competition.days_away < 0:
        prompts.append("Competition date is in the past; confirm the next competition.")
    if latest is None:
        prompts.append("Record a current bodyweight before planning change.")
    if not weight_class:
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
        weight_class=weight_class,
        latest=latest,
        recent=recent,
        target_bodyweight_kg=target,
        change_required_kg=change,
        weeks_available=weeks,
        required_change_per_week_kg=weekly,
        prompts=tuple(prompts),
    )


def build_competition_dashboard_contexts(
    athlete_ids,
    *,
    as_of: date,
    target_bodyweights_kg: dict[int, Decimal | float | str | None] | None = None,
    history_limit: int = 8,
) -> dict[int, AthleteCompetitionDashboardContext]:
    """Load bodyweight and competition context for an authorised athlete set.

    The caller supplies the athlete IDs it is authorised to display. All related
    records are loaded in four bounded queries, rather than once per athlete.
    Missing IDs are omitted and no cross-athlete records are returned.
    """
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    ids = tuple(dict.fromkeys(int(item) for item in athlete_ids))
    if not ids:
        return {}
    targets = target_bodyweights_kg or {}
    unexpected_targets = set(targets) - set(ids)
    if unexpected_targets:
        raise ValueError("target bodyweights must be scoped to requested athletes")

    athletes = Athlete.query.filter(Athlete.id.in_(ids)).all()
    athlete_by_id = {item.id: item for item in athletes}
    meet_rows = (
        MeetEntry.query.join(Meet)
        .options(contains_eager(MeetEntry.meet))
        .filter(
            MeetEntry.athlete_id.in_(athlete_by_id),
            Meet.status.in_(("planned", "active")),
            Meet.meet_date >= as_of,
        )
        .order_by(MeetEntry.athlete_id, Meet.meet_date, Meet.id)
        .all()
        if athlete_by_id
        else []
    )
    weekly = (
        WeeklyCheckin.query.filter(
            WeeklyCheckin.athlete_id.in_(athlete_by_id),
            WeeklyCheckin.week_ending <= as_of,
            WeeklyCheckin.average_bodyweight_kg.isnot(None),
        ).all()
        if athlete_by_id
        else []
    )
    nutrition = (
        NutritionCheckIn.query.filter(
            NutritionCheckIn.athlete_id.in_(athlete_by_id),
            NutritionCheckIn.checkin_date <= as_of,
            NutritionCheckIn.bodyweight_kg.isnot(None),
        ).all()
        if athlete_by_id
        else []
    )

    meet_by_athlete: dict[int, Meet] = {}
    for entry in meet_rows:
        meet_by_athlete.setdefault(entry.athlete_id, entry.meet)
    history_by_athlete: dict[int, list[BodyweightObservation]] = {
        athlete_id: [] for athlete_id in athlete_by_id
    }
    for item in weekly:
        history_by_athlete[item.athlete_id].append(
            BodyweightObservation(
                item.week_ending,
                _kg(item.average_bodyweight_kg),
                "weekly_checkin",
                f"weekly_checkin:{item.id}",
            )
        )
    for item in nutrition:
        history_by_athlete[item.athlete_id].append(
            BodyweightObservation(
                item.checkin_date,
                _kg(item.bodyweight_kg),
                "nutrition_checkin",
                f"nutrition_checkin:{item.id}",
            )
        )

    result = {}
    for athlete_id in ids:
        athlete = athlete_by_id.get(athlete_id)
        if athlete is None:
            continue
        observations = history_by_athlete[athlete_id]
        observations.sort(key=lambda item: (item.recorded_on, item.source_ref))
        recent = tuple(observations[-history_limit:])
        planning = _build_context(
            athlete,
            as_of=as_of,
            target_bodyweight_kg=targets.get(athlete_id),
            competition=_competition_reference_from(
                athlete, as_of, meet_by_athlete.get(athlete_id)
            ),
            recent=recent,
        )
        result[athlete_id] = AthleteCompetitionDashboardContext(
            athlete_id=athlete_id,
            bodyweight=planning,
            trend=_trend(recent, planning.latest),
        )
    return result


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
    return _competition_reference_from(athlete, as_of, entry.meet if entry else None)


def _competition_reference_from(
    athlete, as_of: date, meet: Meet | None
) -> CompetitionReference:
    if meet is not None:
        return CompetitionReference(
            meet.name, meet.meet_date, "meet_entry", f"meet:{meet.id}",
            (meet.meet_date - as_of).days,
            meet.federation, meet.weight_class, meet.status,
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
        athlete.federation,
        athlete.weight_class,
    )


def _trend(
    recent: tuple[BodyweightObservation, ...],
    latest: BodyweightObservation | None,
) -> BodyweightTrend:
    if len(recent) >= 2:
        change = _kg(recent[-1].bodyweight_kg - recent[0].bodyweight_kg)
        return BodyweightTrend(
            status="available",
            change_kg=change,
            span_days=(recent[-1].recorded_on - recent[0].recorded_on).days,
            direction="up" if change > 0 else "down" if change < 0 else "stable",
        )
    if len(recent) == 1:
        return BodyweightTrend("single_observation", None, None, None)
    if latest is not None:
        return BodyweightTrend("profile_only", None, None, None)
    return BodyweightTrend("unavailable", None, None, None)


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
