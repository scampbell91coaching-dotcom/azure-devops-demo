from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import joinedload

from ..models.athlete import Athlete
from ..models.checkins import WeeklyCheckin
from ..models.nutrition_checkin import NutritionCheckIn


@dataclass(frozen=True)
class NutritionRecord:
    recorded_on: date
    submitted_at: datetime
    source: str
    calories: int | None
    protein_g: int | None
    bodyweight_kg: float | None
    adherence: int | None


@dataclass(frozen=True)
class AthleteNutritionSummary:
    athlete: Athlete
    latest: NutritionRecord | None
    latest_weekly: NutritionRecord | None
    recent_bodyweights: tuple[NutritionRecord, ...]
    last_recorded_at: datetime | None

    @property
    def has_recorded_data(self) -> bool:
        return self.latest is not None


@dataclass(frozen=True)
class NutritionDashboard:
    athletes: tuple[AthleteNutritionSummary, ...]

    @property
    def logged_count(self) -> int:
        return sum(item.has_recorded_data for item in self.athletes)


def _checkin_record(item: NutritionCheckIn) -> NutritionRecord:
    return NutritionRecord(
        recorded_on=item.submitted_at.date(),
        submitted_at=item.submitted_at,
        source="Nutrition check-in",
        calories=item.average_calories,
        protein_g=item.average_protein_g,
        bodyweight_kg=item.bodyweight_kg,
        adherence=item.nutrition_adherence,
    )


def _weekly_record(item: WeeklyCheckin) -> NutritionRecord:
    return NutritionRecord(
        recorded_on=item.week_ending,
        submitted_at=item.submitted_at,
        source="Weekly check-in",
        calories=item.calories_average,
        protein_g=item.protein_average_g,
        bodyweight_kg=item.average_bodyweight_kg,
        adherence=item.nutrition_adherence,
    )


def get_nutrition_dashboard() -> NutritionDashboard:
    athletes = Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all()
    athlete_ids = [athlete.id for athlete in athletes]

    dedicated = (
        NutritionCheckIn.query.options(joinedload(NutritionCheckIn.athlete))
        .filter(NutritionCheckIn.athlete_id.in_(athlete_ids))
        .all()
        if athlete_ids
        else []
    )
    weekly = (
        WeeklyCheckin.query.options(joinedload(WeeklyCheckin.athlete))
        .filter(
            WeeklyCheckin.athlete_id.in_(athlete_ids),
            WeeklyCheckin.nutrition_included.is_(True),
        )
        .all()
        if athlete_ids
        else []
    )

    records_by_athlete: dict[int, list[NutritionRecord]] = {
        athlete_id: [] for athlete_id in athlete_ids
    }
    weekly_by_athlete: dict[int, list[NutritionRecord]] = {
        athlete_id: [] for athlete_id in athlete_ids
    }
    for item in dedicated:
        records_by_athlete[item.athlete_id].append(_checkin_record(item))
    for item in weekly:
        record = _weekly_record(item)
        records_by_athlete[item.athlete_id].append(record)
        weekly_by_athlete[item.athlete_id].append(record)

    summaries = []
    for athlete in athletes:
        records = sorted(
            records_by_athlete[athlete.id],
            key=lambda record: (
                record.recorded_on,
                record.submitted_at,
            ),
            reverse=True,
        )
        weekly_records = sorted(
            weekly_by_athlete[athlete.id],
            key=lambda record: (record.recorded_on, record.submitted_at),
            reverse=True,
        )
        bodyweights = tuple(
            record for record in records if record.bodyweight_kg is not None
        )[:4]
        summaries.append(
            AthleteNutritionSummary(
                athlete=athlete,
                latest=records[0] if records else None,
                latest_weekly=weekly_records[0] if weekly_records else None,
                recent_bodyweights=bodyweights,
                last_recorded_at=(
                    max(record.submitted_at for record in records) if records else None
                ),
            )
        )

    return NutritionDashboard(athletes=tuple(summaries))
