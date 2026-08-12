"""Chart-ready athlete performance data from persisted coaching records."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models.athlete import Athlete
from ..models.meet_day import Meet, MeetEntry
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
        if filters.end == date.max:
            raise ValueError("to must be before 9999-12-31")
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

        raw_rows = self._training_rows(athlete_id, filters)
        rows, quality = self._eligible_training_rows(raw_rows)
        bodyweight = build_bodyweight_planning_context(
            athlete, as_of=filters.end, history_limit=200
        )
        e1rm = self._e1rm(rows)
        volume = self._volume(rows)
        rpe = self._rpe(rows)
        meet_trends = self._meet_trends(athlete_id, filters)
        block_comparisons = self._block_comparisons(athlete_id, filters)
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
                "meet_trends": meet_trends,
                "block_comparisons": block_comparisons,
            },
            "availability": {
                "e1rm": self._availability(e1rm, quality),
                "volume": self._availability(volume, quality),
                "rpe": self._availability(rpe, quality),
                "bodyweight": "available" if bodyweight_points else "insufficient_data",
                "meet_trends": "available" if meet_trends else "insufficient_data",
                "block_comparisons": "available" if block_comparisons else "insufficient_data",
            },
            "data_quality": quality,
        }

    @staticmethod
    def _availability(points: list[dict], quality: dict) -> str:
        if not points:
            return "insufficient_data"
        return "partial" if quality["excluded_partial_sessions"] else "available"

    @staticmethod
    def _training_rows(athlete_id: int, filters: PerformanceChartFilter) -> list:
        query = (
            db.session.query(
                TrainingSetResult,
                TrainingSessionLog.id,
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

    @staticmethod
    def _eligible_training_rows(rows: list) -> tuple[list, dict]:
        """Exclude a whole log when its persisted set decisions are incomplete.

        A completed status alone is not enough evidence: every snapshotted result
        must be explicitly completed or skipped. This prevents the completed
        fragments of a partially logged session from looking decision-grade.
        """
        incomplete_logs = {
            log_id
            for result, log_id, _completed_at, _role, _lift in rows
            if not result.completed and not result.skipped
        }
        eligible = [
            (result, completed_at, role, lift)
            for result, log_id, completed_at, role, lift in rows
            if log_id not in incomplete_logs
        ]
        return eligible, {
            "completed_sessions_seen": len({row[1] for row in rows}),
            "eligible_sessions": len({row[1] for row in rows} - incomplete_logs),
            "excluded_partial_sessions": len(incomplete_logs),
            "excluded_set_results": sum(row[1] in incomplete_logs for row in rows),
            "explanation": (
                "Completed sessions with any set result neither completed nor skipped "
                "are excluded from training evidence."
            ),
        }

    @staticmethod
    def _meet_trends(athlete_id: int, filters: PerformanceChartFilter) -> list[dict]:
        rows = (
            db.session.query(MeetEntry, Meet)
            .options(selectinload(MeetEntry.lifts))
            .join(Meet, Meet.id == MeetEntry.meet_id)
            .filter(
                MeetEntry.athlete_id == athlete_id,
                Meet.status == "complete",
                Meet.meet_date >= filters.start,
                Meet.meet_date <= filters.end,
            )
            .order_by(Meet.meet_date, Meet.id)
            .all()
        )
        trends = []
        for entry, meet in rows:
            best = {}
            for lift in entry.lifts:
                if lift.kind == "attempt" and lift.outcome == "good" and lift.weight_kg is not None:
                    best[lift.lift] = max(best.get(lift.lift, 0), float(lift.weight_kg))
            trends.append({
                "date": meet.meet_date.isoformat(),
                "meet_id": meet.id,
                "meet_name": meet.name,
                "best_lifts_kg": {lift: best.get(lift) for lift in ("squat", "bench", "deadlift")},
                "total_kg": round(sum(best.values()), 2) if len(best) == 3 else None,
                "complete_total": len(best) == 3,
            })
        return trends

    @classmethod
    def _block_comparisons(
        cls, athlete_id: int, filters: PerformanceChartFilter
    ) -> list[dict]:
        """Return like-for-like SBD summaries for blocks intersecting the window."""
        raw = (
            db.session.query(
                TrainingSetResult,
                TrainingSessionLog.id,
                TrainingSessionLog.completed_at,
                ExercisePrescription.slot_role,
                ProgrammingLiftSlot.lift_family,
                TrainingBlock.id,
                TrainingBlock.name,
            )
            .join(TrainingSessionLog, TrainingSetResult.session_log_id == TrainingSessionLog.id)
            .join(TrainingSession, TrainingSessionLog.session_id == TrainingSession.id)
            .join(TrainingWeek, TrainingSession.week_id == TrainingWeek.id)
            .join(TrainingBlock, TrainingWeek.block_id == TrainingBlock.id)
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
                TrainingSessionLog.completed_at >= datetime.combine(filters.start, time.min),
                TrainingSessionLog.completed_at
                < datetime.combine(filters.end + timedelta(days=1), time.min),
            )
            .order_by(TrainingBlock.id, TrainingSessionLog.completed_at, TrainingSetResult.id)
            .all()
        )
        grouped: dict[tuple[int, str], list] = defaultdict(list)
        for result, log_id, completed_at, role, lift, block_id, block_name in raw:
            grouped[(block_id, block_name)].append((result, log_id, completed_at, role, lift))
        comparisons = []
        for (block_id, block_name), block_rows in grouped.items():
            eligible, quality = cls._eligible_training_rows(block_rows)
            lift_volume = {lift: 0.0 for lift in ("squat", "bench", "deadlift")}
            for point in cls._volume(eligible):
                lift_volume[point["lift"]] += point["value_kg"]
            best_e1rm = {lift: None for lift in ("squat", "bench", "deadlift")}
            for point in cls._e1rm(eligible):
                lift = point["lift"]
                best_e1rm[lift] = max(best_e1rm[lift] or 0, point["value_kg"])
            comparisons.append({
                "block_id": block_id,
                "block_name": block_name,
                "volume_kg": {lift: round(value, 2) for lift, value in lift_volume.items()},
                "best_e1rm_kg": best_e1rm,
                "eligible_sessions": quality["eligible_sessions"],
                "excluded_partial_sessions": quality["excluded_partial_sessions"],
            })
        return comparisons

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
