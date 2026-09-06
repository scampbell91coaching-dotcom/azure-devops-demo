from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..models.athlete_state import AthleteStateFact, AthleteStateOverride
from ..models.checkins import WeeklyCheckin
from ..models.meet_day import Meet, MeetEntry
from ..models.programming import TrainingBlock, TrainingSessionLog
from .programming_athlete_state import aggregate_programming_athlete_state


def programming_review_context(block: TrainingBlock) -> dict[str, Any]:
    """Compose existing evidence for review; never mutates programming or state."""
    athlete_id = block.athlete_id
    state = aggregate_programming_athlete_state(block.athlete)
    facts = (AthleteStateFact.query.filter_by(athlete_id=athlete_id)
             .order_by(AthleteStateFact.recorded_at.desc()).limit(8).all())
    latest_fact = facts[0] if facts else None
    updated = latest_fact.recorded_at if latest_fact else None
    age = datetime.now(UTC).replace(tzinfo=None) - updated if updated else None
    freshness = "missing" if updated is None else "fresh" if age <= timedelta(days=7) else "stale"
    checkin = (WeeklyCheckin.query.filter_by(athlete_id=athlete_id)
               .order_by(WeeklyCheckin.week_ending.desc(), WeeklyCheckin.id.desc()).first())
    session_ids = [session.id for week in block.weeks for session in week.sessions]
    logs = (TrainingSessionLog.query.filter(TrainingSessionLog.athlete_id == athlete_id,
            TrainingSessionLog.session_id.in_(session_ids)).order_by(TrainingSessionLog.updated_at.desc()).all()
            if session_ids else [])
    meet_entries = (MeetEntry.query.join(Meet).filter(MeetEntry.athlete_id == athlete_id)
                    .order_by(Meet.meet_date.desc()).all())
    now = datetime.now(UTC).replace(tzinfo=None)
    pins = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == athlete_id,
        AthleteStateOverride.revoked_at.is_(None),
        (AthleteStateOverride.expires_at.is_(None)) | (AthleteStateOverride.expires_at > now),
    ).order_by(AthleteStateOverride.recorded_at.desc()).all()
    incomplete = []
    for week in block.weeks:
        if not week.sessions:
            incomplete.append(f"Week {week.position} has no sessions")
        for session in week.sessions:
            if not session.prescriptions:
                incomplete.append(f"Week {week.position} · {session.name} has no work prescribed")
            incomplete.extend(
                f"Week {week.position} · {session.name} · {row.exercise_name} is incomplete"
                for row in session.prescriptions if not row.summary
            )
    return {"state": state, "facts": facts, "state_updated": updated, "freshness": freshness,
            "latest_checkin": checkin, "logs": logs, "meets": meet_entries,
            "pins": pins, "incomplete": incomplete}
