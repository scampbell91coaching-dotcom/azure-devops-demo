from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import selectinload

from ..models.checkins import AthleteCheckinSettings
from ..models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingWeek,
)
from .athlete_dashboard import get_athlete_dashboard
from .checkins import athlete_checkins

CONTRACT_VERSION = "athlete.v1"


def envelope(data: Any) -> dict[str, Any]:
    """Wrap every mobile contract response in an explicitly versioned envelope."""
    return {"contract_version": CONTRACT_VERSION, "data": data}


def iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def today_dto(athlete_id: int, *, today: date) -> dict[str, Any] | None:
    dashboard = get_athlete_dashboard(athlete_id, today=today)
    if dashboard is None:
        return None
    scheduled = dashboard.today_session or dashboard.next_scheduled_session
    return {
        "date": today.isoformat(),
        "athlete": {
            "display_name": dashboard.athlete.full_name,
            "bodyweight_kg": dashboard.latest_bodyweight_kg,
            "weight_class": dashboard.athlete.weight_class,
            "federation": dashboard.athlete.federation,
        },
        "training": {
            "current_block": (
                {"id": dashboard.current_block.id, "name": dashboard.current_block.name}
                if dashboard.current_block else None
            ),
            "session": _scheduled_session_dto(scheduled),
        },
        "check_in": {
            "next_due_on": iso(dashboard.next_checkin_date),
            "latest_submitted_on": (
                iso(dashboard.latest_checkin.submitted_at)
                if dashboard.latest_checkin else None
            ),
        },
        "coach_response": (
            {
                "body": dashboard.latest_coach_response.body,
                "responded_at": iso(dashboard.latest_coach_response.responded_at),
            }
            if dashboard.latest_coach_response else None
        ),
    }


def programme_dto(athlete_id: int) -> dict[str, Any] | None:
    block = (
        TrainingBlock.query.options(
            selectinload(TrainingBlock.weeks)
            .selectinload(TrainingWeek.sessions)
            .selectinload(TrainingSession.prescriptions)
        )
        .filter_by(athlete_id=athlete_id, status="active")
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    if block is None:
        return None
    logs = {
        item.session_id: item
        for item in TrainingSessionLog.query.filter_by(athlete_id=athlete_id).all()
    }
    return {
        "id": block.id,
        "name": block.name,
        "objective": block.objective,
        "status": block.status,
        "weeks": [
            {
                "id": week.id,
                "name": week.name,
                "position": week.position,
                "sessions": [
                    _session_summary_dto(session, logs.get(session.id))
                    for session in week.sessions
                ],
            }
            for week in block.weeks
        ],
    }


def session_dto(athlete_id: int, session_id: int) -> dict[str, Any] | None:
    session = (
        TrainingSession.query.join(TrainingWeek).join(TrainingBlock)
        .options(selectinload(TrainingSession.prescriptions))
        .filter(
            TrainingSession.id == session_id,
            TrainingBlock.athlete_id == athlete_id,
            TrainingBlock.status == "active",
        )
        .first()
    )
    if session is None:
        return None
    log = TrainingSessionLog.query.filter_by(
        athlete_id=athlete_id, session_id=session_id
    ).one_or_none()
    results = {
        (item.exercise_position, item.set_order): item
        for item in (log.results if log else ())
    }
    return {
        **_session_summary_dto(session, log),
        "notes": session.notes,
        "exercises": [
            _prescription_dto(item, results) for item in session.prescriptions
        ],
    }


def checkins_dto(athlete_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "week_ending": iso(item.week_ending),
            "submitted_at": iso(item.submitted_at),
            "status": item.status,
            "training": {
                "included": item.training_included,
                "adherence": item.training_adherence,
                "fatigue": item.fatigue,
                "recovery": item.recovery,
                "motivation": item.motivation,
                "pain_present": item.pain_present,
                "notes": item.training_notes,
            },
            "recovery": {"sleep_quality": item.sleep_quality, "stress": item.stress},
            "coach_response": item.coach_notes,
        }
        for item in athlete_checkins(athlete_id)
    ]


def progress_dto(athlete_id: int, *, today: date) -> dict[str, Any] | None:
    dashboard = get_athlete_dashboard(athlete_id, today=today)
    if dashboard is None:
        return None
    completed = (
        TrainingSessionLog.query.filter_by(athlete_id=athlete_id, status="completed")
        .order_by(TrainingSessionLog.completed_at.desc())
        .limit(20)
        .all()
    )
    return {
        "bodyweight_kg": [
            {"date": point.recorded_on.isoformat(), "value": point.value}
            for point in dashboard.bodyweight_trend
        ],
        "completed_sessions": [
            {
                "id": item.id,
                "session_name": item.session_name,
                "block_name": item.block_name,
                "week_name": item.week_name,
                "completed_at": iso(item.completed_at),
            }
            for item in completed
        ],
    }


def meal_plan_dto(assignment: Any) -> dict[str, Any]:
    return {
        "id": assignment.assignment_id,
        "name": assignment.template_name,
        "revision": assignment.template_revision,
        "effective_from": iso(assignment.effective_from),
        "effective_until": iso(assignment.effective_until),
        "published_at": iso(assignment.published_at),
        "days": [
            {
                "id": day.day_id,
                "name": day.name,
                "position": day.position,
                "mode": day.mode.value,
                "planned_macros": _macro_dto(day.planned_macros),
                "meals": [
                    {
                        "id": meal.meal_id,
                        "name": meal.name,
                        "position": meal.position,
                        "note": meal.note,
                        "items": [
                            {
                                "id": item.item_id,
                                "name": item.food.name,
                                "amount": str(item.amount),
                                "unit": item.food.unit,
                                "note": item.note,
                            }
                            for item in meal.items
                        ],
                    }
                    for meal in day.meals
                ],
            }
            for day in assignment.days
        ],
        # PDF export is intentionally capability-shaped until an immutable
        # athlete-owned artifact exists. A client must not fabricate a URL.
        "pdf": {"status": "unavailable", "download_url": None},
    }


def checkin_settings(athlete_id: int) -> AthleteCheckinSettings | None:
    return AthleteCheckinSettings.query.filter_by(athlete_id=athlete_id).first()


def _scheduled_session_dto(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.session.id,
        "name": item.session.name,
        "day_label": item.session.day_label,
        "planned_for": iso(item.planned_on),
        "state": "completed" if item.completed else "scheduled",
    }


def _session_summary_dto(
    session: TrainingSession, log: TrainingSessionLog | None
) -> dict[str, Any]:
    return {
        "id": session.id,
        "name": session.name,
        "day_label": session.day_label,
        "position": session.position,
        "log": (
            {"id": log.id, "status": log.status, "updated_at": iso(log.updated_at)}
            if log else None
        ),
    }


def _prescription_dto(
    item: ExercisePrescription, results: dict[tuple[int, int], Any]
) -> dict[str, Any]:
    return {
        "id": item.id,
        "exercise_name": item.exercise_name,
        "position": item.position,
        "prescription": item.summary,
        "sets": [
            {
                "order": order,
                "completed": bool(result and result.completed),
                "skipped": bool(result and result.skipped),
                "load_kg": result.actual_load_kg if result else None,
                "reps": result.actual_reps if result else None,
                "rpe": result.actual_rpe if result else None,
                "note": result.athlete_note if result else None,
            }
            for order in range(1, (item.sets or 1) + 1)
            for result in [results.get((item.position, order))]
        ],
    }


def _macro_dto(value: Any) -> dict[str, str]:
    fields = ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g")
    return {
        name: str(getattr(value, name).quantize(Decimal("0.01"))) for name in fields
    }
