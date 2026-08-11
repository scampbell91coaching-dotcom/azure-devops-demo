"""Chart-ready athlete performance data from persisted coaching records."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from .competition_bodyweight import build_bodyweight_planning_context


@dataclass(frozen=True)
class PerformanceChartFilter:
    start: date
    end: date
    block_id: int | None = None


class AthletePerformanceChartService:
    """Build presentation data without granting or inferring athlete access."""

    def build(self, athlete_id: int, filters: PerformanceChartFilter) -> dict:
        if filters.end < filters.start:
            raise ValueError("to must be on or after from")
        if (filters.end - filters.start).days > 730:
            raise ValueError("date range cannot exceed 731 days")
        athlete = db.session.get(Athlete, athlete_id)
        if athlete is None:
            raise LookupError("athlete not found")

        block = None
        if filters.block_id is not None:
            block = db.session.get(TrainingBlock, filters.block_id)
            if block is None or block.athlete_id != athlete_id:
                raise LookupError("block not found")

        rows = self._training_rows(athlete_id, filters)
        bodyweight = build_bodyweight_planning_context(
            athlete, as_of=filters.end, history_limit=200
        )
        e1rm = self._e1rm(rows)
        volume = self._volume(rows)
        rpe = self._rpe(rows)
        bodyweight_points = [
            {
                "date": point.recorded_on.isoformat(),
                "value_kg": float(point.bodyweight_kg),
                "source": point.source,
                "source_ref": point.source_ref,
            }
            for point in bodyweight.recent
            if point.recorded_on is not None
            and filters.start <= point.recorded_on <= filters.end
        ]
        return {
            "athlete_id": athlete.id,
            "filters": {
                "from": filters.start.isoformat(),
                "to": filters.end.isoformat(),
                "block_id": filters.block_id,
                "block_name": block.name if block is not None else None,
            },
            "datasets": {
                "e1rm": e1rm,
                "volume": volume,
                "rpe": rpe,
                "bodyweight": bodyweight_points,
            },
            "availability": {
                "e1rm": "available" if e1rm else "insufficient_data",
                "volume": "available" if volume else "insufficient_data",
                "rpe": "available" if rpe else "insufficient_data",
                "bodyweight": "available" if bodyweight_points else "insufficient_data",
            },
        }

    @staticmethod
    def _training_rows(athlete_id: int, filters: PerformanceChartFilter) -> list:
        query = (
            db.session.query(
                TrainingSetResult,
                TrainingSessionLog.completed_at,
                ExercisePrescription.slot_role,
                ProgrammingLiftSlot.lift_family,
            )
            .join(
                TrainingSessionLog,
                TrainingSetResult.session_log_id == TrainingSessionLog.id,
            )
            .outerjoin(
                ExercisePrescription,
                TrainingSetResult.prescription_id == ExercisePrescription.id,
            )
            .outerjoin(
                ProgrammingLiftSlot,
                ExercisePrescription.lift_slot_id == ProgrammingLiftSlot.id,
            )
            .filter(
                TrainingSessionLog.athlete_id == athlete_id,
                TrainingSessionLog.status == "completed",
                TrainingSessionLog.completed_at
                >= datetime.combine(filters.start, time.min),
                TrainingSessionLog.completed_at
                < datetime.combine(filters.end + timedelta(days=1), time.min),
            )
        )
        if filters.block_id is not None:
            query = (
                query.join(
                    TrainingSession,
                    TrainingSessionLog.session_id == TrainingSession.id,
                )
                .join(TrainingWeek, TrainingSession.week_id == TrainingWeek.id)
                .filter(TrainingWeek.block_id == filters.block_id)
            )
        return query.order_by(
            TrainingSessionLog.completed_at, TrainingSetResult.id
        ).all()

    @classmethod
    def _e1rm(cls, rows: list) -> list[dict]:
        best: dict[tuple[date, str], dict] = {}
        for result, started_at, slot_role, lift in rows:
            if not (
                lift in ("squat", "bench", "deadlift")
                and slot_role == "top_set"
                and result.completed
                and result.actual_load_kg is not None
                and result.actual_load_kg > 0
                and result.actual_reps is not None
                and 0 < result.actual_reps <= 12
            ):
                continue
            estimate = round(result.actual_load_kg * (1 + result.actual_reps / 30), 2)
            key = (started_at.date(), lift)
            point = {
                "date": key[0].isoformat(),
                "lift": lift,
                "value_kg": estimate,
                "result_id": result.id,
                "top_set": True,
            }
            if key not in best or estimate > best[key]["value_kg"]:
                best[key] = point
        return [best[key] for key in sorted(best)]

    @classmethod
    def _volume(cls, rows: list) -> list[dict]:
        totals: dict[tuple[date, str], float] = defaultdict(float)
        for result, started_at, _, lift in rows:
            if (
                lift in ("squat", "bench", "deadlift")
                and result.completed
                and result.actual_load_kg is not None
                and result.actual_load_kg > 0
                and result.actual_reps is not None
                and result.actual_reps > 0
            ):
                totals[(started_at.date(), lift)] += result.actual_load_kg * result.actual_reps
        return [
            {"date": day.isoformat(), "lift": lift, "value_kg": round(value, 2)}
            for (day, lift), value in sorted(totals.items())
        ]

    @staticmethod
    def _rpe(rows: list) -> list[dict]:
        points = []
        for result, started_at, _, _ in rows:
            if not (
                result.completed
                and result.actual_rpe is not None
                and result.prescribed_rpe is not None
            ):
                continue
            delta = round(result.actual_rpe - result.prescribed_rpe, 2)
            points.append(
                {
                    "date": started_at.date().isoformat(),
                    "result_id": result.id,
                    "exercise": result.exercise_name,
                    "prescribed": result.prescribed_rpe,
                    "actual": result.actual_rpe,
                    "delta": delta,
                    "adherent": abs(delta) <= 0.5,
                }
            )
        return points
