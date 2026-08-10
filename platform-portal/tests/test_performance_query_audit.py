from datetime import UTC, datetime

from sqlalchemy import event

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.client_service import ClientServiceChange
from portal.models.programming import (
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.models.user import User, UserRole
from portal.models.warmup import WarmupAssignment, WarmupProtocol, WarmupProtocolStep
from portal.services.client_services import resolved_client_services
from portal.services.persisted_warmups import resolve_warmup


def _app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
    return app


def _select_count(call):
    count = 0

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal count
        if statement.lstrip().upper().startswith("SELECT"):
            count += 1

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        result = call()
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    return count, result


def _programme(athlete, *, weeks, sessions_per_week=3):
    block = TrainingBlock(athlete=athlete, name=f"{weeks} week block")
    for week_number in range(weeks):
        week = TrainingWeek(block=block, name=f"Week {week_number + 1}", position=week_number + 1)
        for session_number in range(sessions_per_week):
            session = TrainingSession(week=week, name="Training", position=session_number + 1)
            session.lift_slots.append(
                ProgrammingLiftSlot(position=1, lift_family="squat")
            )
    db.session.add(block)
    db.session.flush()
    return block


def test_block_page_select_count_does_not_grow_with_programme_length():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        short = _programme(athlete, weeks=1)
        long = _programme(athlete, weeks=8)
        db.session.commit()
        short_id, long_id = short.id, long.id
        client = app.test_client()

        db.session.expire_all()
        short_count, short_response = _select_count(
            lambda: client.get(f"/programming/blocks/{short_id}")
        )
        db.session.expire_all()
        long_count, long_response = _select_count(
            lambda: client.get(f"/programming/blocks/{long_id}")
        )

        assert short_response.status_code == long_response.status_code == 200
        assert long_count == short_count


def test_resolved_services_loads_history_and_provenance_in_one_select():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        coaches = [
            User(email=f"coach-{number}@test", role=UserRole.COACH)
            for number in range(4)
        ]
        db.session.add_all([athlete, *coaches])
        db.session.flush()
        for number, coach in enumerate(coaches):
            db.session.add(
                ClientServiceChange(
                    athlete_id=athlete.id,
                    service=("training", "nutrition", "meet_day", "video_review")[number],
                    value=("yes", "yes", "yes", "included")[number],
                    effective_at=datetime(2026, 8, number + 1),
                    changed_by_user_id=coach.id,
                )
            )
        db.session.commit()
        athlete_id = athlete.id
        db.session.expire_all()

        count, services = _select_count(
            lambda: resolved_client_services(
                athlete_id, now=datetime(2026, 8, 10, tzinfo=UTC)
            )
        )

        assert count == 1
        assert {item["provenance"] for item in services} == {
            coach.email for coach in coaches
        }


def test_warmup_resolution_select_count_is_constant_across_protocols():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        block = _programme(athlete, weeks=1, sessions_per_week=2)
        db.session.flush()
        short_session, long_session = block.weeks[0].sessions
        for number in range(6):
            protocol = WarmupProtocol(
                stable_key=f"protocol-{number}", version=1, name=f"Protocol {number}"
            )
            protocol.steps.append(
                WarmupProtocolStep(
                    position=1, phase=10, name="Bike", kind="duration", sets=1,
                    duration_seconds=60,
                )
            )
            db.session.add(protocol)
            db.session.flush()
            target = short_session if number == 0 else long_session
            db.session.add(
                WarmupAssignment(
                    protocol_id=protocol.id, athlete_id=athlete.id,
                    session_id=target.id, reason="Coach selected",
                )
            )
        db.session.commit()
        athlete_id = athlete.id
        short_session_id = short_session.id
        long_session_id = long_session.id

        db.session.expire_all()
        short_count, short_steps = _select_count(
            lambda: resolve_warmup(athlete_id, short_session_id)
        )
        db.session.expire_all()
        long_count, long_steps = _select_count(
            lambda: resolve_warmup(athlete_id, long_session_id)
        )

        assert len(short_steps) == 1
        assert len(long_steps) == 5
        assert long_count == short_count == 4
