from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import selectinload

from ..models.athlete import Athlete
from ..models.checkins import AthleteCheckinSettings, WeeklyCheckin
from ..models.nutrition_checkin import NutritionCheckIn
from ..models.programming import TrainingBlock, TrainingSessionLog


@dataclass(frozen=True)
class ReviewItem:
    athlete: Athlete
    kind: str
    submitted_at: datetime
    url_kind: str
    item_id: int
    summary: str | None = None
    review_state: str = "Needs review"


@dataclass(frozen=True)
class DueCheckin:
    athlete: Athlete
    due_date: date


@dataclass(frozen=True)
class AthleteFlag:
    athlete: Athlete
    checkin: WeeklyCheckin
    flags: tuple[str, ...]


@dataclass(frozen=True)
class NutritionSummary:
    athlete: Athlete
    recorded_at: date
    bodyweight_kg: float | None
    calories: int | None
    protein_g: int | None
    source: str


@dataclass(frozen=True)
class CoachDashboard:
    requiring_review: tuple[ReviewItem, ...]
    recent_checkins: tuple[WeeklyCheckin, ...]
    pending_checkins: tuple[DueCheckin, ...]
    health_flags: tuple[AthleteFlag, ...]
    programmes_ending_soon: tuple[TrainingBlock, ...]
    programme_timing_available: bool
    nutrition: tuple[NutritionSummary, ...]
    without_programme: tuple[Athlete, ...]


class CoachDashboardService:
    """Build the coach's daily review view from existing platform records."""

    RECENT_DAYS = 14

    def build(self, *, today: date | None = None) -> CoachDashboard:
        today = today or datetime.now(UTC).date()
        athletes = Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all()
        weekly = WeeklyCheckin.query.order_by(
            WeeklyCheckin.submitted_at.desc(), WeeklyCheckin.id.desc()
        ).all()
        nutrition = NutritionCheckIn.query.order_by(
            NutritionCheckIn.submitted_at.desc(), NutritionCheckIn.id.desc()
        ).all()
        training_logs = (
            TrainingSessionLog.query.options(selectinload(TrainingSessionLog.results))
            .filter_by(status="completed")
            .filter(TrainingSessionLog.completed_at.is_not(None))
            .order_by(TrainingSessionLog.completed_at.asc(), TrainingSessionLog.id.asc())
            .all()
        )
        settings = AthleteCheckinSettings.query.order_by(
            AthleteCheckinSettings.athlete_id
        ).all()
        blocks = TrainingBlock.query.order_by(
            TrainingBlock.created_at.desc(), TrainingBlock.id.desc()
        ).all()

        athlete_by_id = {athlete.id: athlete for athlete in athletes}
        explicit_settings = {item.athlete_id: item for item in settings}
        nutrition_enabled_ids = {
            athlete.id
            for athlete in athletes
            if athlete.id not in explicit_settings
            or explicit_settings[athlete.id].nutrition_enabled
        }
        recent_cutoff = today - timedelta(days=self.RECENT_DAYS - 1)
        recent = tuple(item for item in weekly if item.week_ending >= recent_cutoff)

        requiring_review = self._reviews(
            athlete_by_id, weekly, nutrition, training_logs, nutrition_enabled_ids
        )
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        submitted_athlete_ids = {
            item.athlete_id
            for item in weekly
            if week_start <= item.week_ending <= week_end
        }
        pending = tuple(
            DueCheckin(athlete_by_id[item.athlete_id], today)
            for item in settings
            if item.athlete_id in athlete_by_id
            and athlete_by_id[item.athlete_id].status == "active"
            and item.workflow_active
            and item.has_enabled_modules
            and item.checkin_day == today.weekday()
            and item.athlete_id not in submitted_athlete_ids
        )
        pending = tuple(
            sorted(
                pending,
                key=lambda item: (
                    item.due_date,
                    item.athlete.last_name.casefold(),
                    item.athlete.first_name.casefold(),
                    item.athlete.id,
                ),
            )
        )
        latest_weekly = self._latest_weekly_by_athlete(weekly)
        health_flags = tuple(
            AthleteFlag(
                athlete=athlete_by_id[athlete_id],
                checkin=item,
                flags=tuple(
                    flag
                    for flag in item.risk_flags
                    if flag in {"High fatigue", "Pain reported"}
                ),
            )
            for athlete_id, item in latest_weekly.items()
            if athlete_id in athlete_by_id
            and any(
                flag in {"High fatigue", "Pain reported"} for flag in item.risk_flags
            )
        )

        current_blocks: dict[int, TrainingBlock] = {}
        for block in blocks:
            if block.status != "archived" and block.athlete_id not in current_blocks:
                current_blocks[block.athlete_id] = block

        # Blocks contain ordered weeks but no dates or current-week marker. An end
        # date cannot be derived faithfully until one of those fields exists.
        programmes_ending_soon: tuple[TrainingBlock, ...] = ()

        return CoachDashboard(
            requiring_review=requiring_review,
            recent_checkins=recent,
            pending_checkins=pending,
            health_flags=health_flags,
            programmes_ending_soon=programmes_ending_soon,
            programme_timing_available=False,
            nutrition=self._nutrition_summaries(athletes, weekly, nutrition),
            without_programme=tuple(
                athlete
                for athlete in athletes
                if athlete.status == "active" and athlete.id not in current_blocks
            ),
        )

    @staticmethod
    def _latest_weekly_by_athlete(
        items: list[WeeklyCheckin],
    ) -> dict[int, WeeklyCheckin]:
        latest: dict[int, WeeklyCheckin] = {}
        for item in items:
            current = latest.get(item.athlete_id)
            if current is None or (
                item.week_ending,
                item.submitted_at,
                item.id,
            ) > (
                current.week_ending,
                current.submitted_at,
                current.id,
            ):
                latest[item.athlete_id] = item
        return latest

    @staticmethod
    def _reviews(
        athletes: dict[int, Athlete],
        weekly: list[WeeklyCheckin],
        nutrition: list[NutritionCheckIn],
        training_logs: list[TrainingSessionLog],
        nutrition_enabled_ids: set[int],
    ) -> tuple[ReviewItem, ...]:
        items = [
            ReviewItem(
                athlete=athletes[item.athlete_id],
                kind="Weekly check-in",
                submitted_at=item.submitted_at,
                url_kind="weekly",
                item_id=item.id,
            )
            for item in weekly
            if item.athlete_id in athletes and item.status == "submitted"
        ]
        items.extend(
            ReviewItem(
                athlete=athletes[item.athlete_id],
                kind="Nutrition check-in",
                submitted_at=item.submitted_at,
                url_kind="nutrition",
                item_id=item.id,
            )
            for item in nutrition
            if item.athlete_id in athletes
            and item.athlete_id in nutrition_enabled_ids
            and not item.reviewed
        )
        items.extend(
            ReviewItem(
                athlete=athletes[item.athlete_id],
                kind=item.session_name,
                submitted_at=item.completed_at,
                url_kind="training",
                item_id=item.id,
                summary=CoachDashboardService._training_summary(item),
            )
            for item in training_logs
            if item.athlete_id in athletes and item.completed_at is not None
        )
        return tuple(
            sorted(
                items,
                key=lambda item: (item.submitted_at, item.url_kind, item.item_id),
            )
        )

    @staticmethod
    def _training_summary(log: TrainingSessionLog) -> str:
        notes = [
            result.athlete_note.strip()
            for result in log.results
            if result.athlete_note and result.athlete_note.strip()
        ]
        if notes:
            return "Notes: " + " · ".join(notes[:2])
        completed = sum(1 for result in log.results if result.completed)
        skipped = sum(1 for result in log.results if result.skipped)
        parts = [f"{completed} set{'s' if completed != 1 else ''} completed"]
        if skipped:
            parts.append(f"{skipped} skipped")
        return " · ".join(parts)

    @staticmethod
    def _nutrition_summaries(
        athletes: list[Athlete],
        weekly: list[WeeklyCheckin],
        nutrition: list[NutritionCheckIn],
    ) -> tuple[NutritionSummary, ...]:
        candidates: dict[int, list[NutritionSummary]] = {}
        for item in weekly:
            if not item.nutrition_included:
                continue
            candidates.setdefault(item.athlete_id, []).append(
                NutritionSummary(
                    athlete=item.athlete,
                    recorded_at=item.week_ending,
                    bodyweight_kg=item.average_bodyweight_kg,
                    calories=item.calories_average,
                    protein_g=item.protein_average_g,
                    source="Weekly check-in",
                )
            )
        for item in nutrition:
            candidates.setdefault(item.athlete_id, []).append(
                NutritionSummary(
                    athlete=item.athlete,
                    recorded_at=item.submitted_at.date(),
                    bodyweight_kg=item.bodyweight_kg,
                    calories=item.average_calories,
                    protein_g=item.average_protein_g,
                    source="Nutrition check-in",
                )
            )

        summaries = []
        for athlete in athletes:
            records = candidates.get(athlete.id, [])
            if records:
                summaries.append(max(records, key=lambda item: item.recorded_at))
            elif athlete.bodyweight_kg is not None:
                summaries.append(
                    NutritionSummary(
                        athlete=athlete,
                        recorded_at=athlete.updated_at.date(),
                        bodyweight_kg=athlete.bodyweight_kg,
                        calories=None,
                        protein_g=None,
                        source="Athlete profile",
                    )
                )
        return tuple(summaries)
