from datetime import date
from decimal import Decimal

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.meet_day import Meet, MeetEntry, MeetLift
from portal.services.meet_day import build_board


@pytest.fixture
def app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "meet-day-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def _athlete(first_name: str, email: str) -> Athlete:
    athlete = Athlete(first_name=first_name, last_name="Lifter", email=email)
    db.session.add(athlete)
    db.session.flush()
    return athlete


def test_board_orders_platform_attempts_and_ignores_warmups(app):
    with app.app_context():
        later = _athlete("Later", "later@example.test")
        next_athlete = _athlete("Next", "next@example.test")
        meet = Meet(name="Nationals", meet_date=date(2026, 8, 8))
        later_entry = MeetEntry(meet=meet, athlete=later, flight=2, platform_order=1)
        next_entry = MeetEntry(
            meet=meet, athlete=next_athlete, flight=1, platform_order=3
        )
        db.session.add_all(
            [
                MeetLift(
                    entry=later_entry,
                    lift="squat",
                    kind="attempt",
                    sequence=1,
                    weight_kg=200,
                ),
                MeetLift(
                    entry=next_entry,
                    lift="squat",
                    kind="warmup",
                    sequence=1,
                    weight_kg=100,
                ),
                MeetLift(
                    entry=next_entry,
                    lift="squat",
                    kind="attempt",
                    sequence=1,
                    weight_kg=180,
                ),
            ]
        )
        db.session.commit()

        board = build_board(meet)

        assert board.next_lift.entry is next_entry
        assert board.next_by_entry[later_entry.id].weight_kg == Decimal("200.00")


def test_routes_validate_create_entry_and_lift_payloads(app):
    client = app.test_client()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.test")
        db.session.commit()
        athlete_id = athlete.id

    assert (
        client.post(
            "/meet-day", data={"name": "", "meet_date": "not-a-date"}
        ).status_code
        == 400
    )
    created = client.post(
        "/meet-day",
        data={"name": "Summer Open", "meet_date": "2026-08-08", "notes": "Rack 12"},
    )
    assert created.status_code == 302
    with app.app_context():
        meet_id = Meet.query.one().id

    invalid_entry = client.post(
        f"/meet-day/{meet_id}/entries",
        data={"athlete_id": athlete_id, "flight": "0", "platform_order": "1"},
    )
    assert invalid_entry.status_code == 400
    assert b"Flight must be at least 1" in invalid_entry.data
    assert (
        client.post(
            f"/meet-day/{meet_id}/entries",
            data={"athlete_id": athlete_id, "flight": "2", "platform_order": "4"},
        ).status_code
        == 302
    )
    with app.app_context():
        entry_id = MeetEntry.query.one().id

    invalid_lift = client.post(
        f"/meet-day/{meet_id}/entries/{entry_id}/lifts",
        data={
            "lift": "squat",
            "kind": "attempt",
            "sequence": "4",
            "weight_kg": "200",
            "outcome": "pending",
        },
    )
    assert invalid_lift.status_code == 400
    assert b"between 1 and 3" in invalid_lift.data


def test_full_coach_workflow_advances_next_lift_and_keeps_notes(app):
    client = app.test_client()
    with app.app_context():
        athlete = _athlete("Sam", "sam@example.test")
        meet = Meet(name="Championship", meet_date=date(2026, 8, 9))
        entry = MeetEntry(meet=meet, athlete=athlete, flight=1, platform_order=2)
        db.session.add_all([meet, entry])
        db.session.commit()
        meet_id, entry_id = meet.id, entry.id

    for sequence, weight in ((1, "190"), (2, "202.5")):
        response = client.post(
            f"/meet-day/{meet_id}/entries/{entry_id}/lifts",
            data={
                "lift": "squat",
                "kind": "attempt",
                "sequence": sequence,
                "weight_kg": weight,
                "outcome": "pending",
                "notes": f"Plan {sequence}",
            },
        )
        assert response.status_code == 302

    page = client.get(f"/meet-day/{meet_id}")
    assert b"Next lift" in page.data
    assert b"Squat 1" in page.data
    with app.app_context():
        first = MeetLift.query.filter_by(sequence=1).one()
        first_id = first.id
    result = client.post(
        f"/meet-day/{meet_id}/lifts/{first_id}",
        data={"weight_kg": "190", "outcome": "good", "notes": "Three whites"},
    )
    assert result.status_code == 302
    page = client.get(f"/meet-day/{meet_id}")
    assert b"Squat 2" in page.data
    assert b"Three whites" in page.data
    with app.app_context():
        first = db.session.get(MeetLift, first_id)
        assert first.outcome == "good"
        assert first.notes == "Three whites"


def test_cross_meet_lift_update_is_not_found(app):
    with app.app_context():
        athlete = _athlete("Jo", "jo@example.test")
        first = Meet(name="First", meet_date=date(2026, 8, 8))
        second = Meet(name="Second", meet_date=date(2026, 8, 9))
        entry = MeetEntry(meet=first, athlete=athlete, flight=1, platform_order=1)
        lift = MeetLift(entry=entry, lift="bench", kind="attempt", sequence=1)
        db.session.add_all([first, second, lift])
        db.session.commit()
        second_id, lift_id = second.id, lift.id

    response = app.test_client().post(
        f"/meet-day/{second_id}/lifts/{lift_id}",
        data={"weight_kg": "100", "outcome": "good"},
    )
    assert response.status_code == 404


def test_create_validation_preserves_values_and_calculators_persist_three_lifts(app):
    client = app.test_client()
    invalid = client.post("/meet-day", data={"name": "Preserved Open", "meet_date": "bad", "federation": "GBPF"})
    assert invalid.status_code == 400
    assert b'value="Preserved Open"' in invalid.data
    assert b'value="GBPF"' in invalid.data
    with app.app_context():
        athlete = _athlete("Taylor", "taylor@example.test")
        meet = Meet(name="Loading Open", meet_date=date(2026, 9, 1))
        entry = MeetEntry(meet=meet, athlete=athlete, flight=1, platform_order=1)
        db.session.add(entry)
        db.session.commit()
        meet_id, entry_id = meet.id, entry.id
    inventory = {f"plate_{plate}": "8" for plate in ("25", "20", "15", "10", "5", "2.5", "1.25", "0.5", "0.25")}
    load = client.post(f"/meet-day/{meet_id}/plate-calculator", data={"target_kg": "202.5", "bar_kg": "20", "collars_kg": "0", **inventory})
    assert load.status_code == 200
    assert b"Per side, load" in load.data
    for lift, opener in (("squat", "200"), ("bench", "120"), ("deadlift", "220")):
        response = client.post(f"/meet-day/{meet_id}/entries/{entry_id}/warmups", data={"lift": lift, "opener_kg": opener, "bar_kg": "20", "collars_kg": "0", "minimum_increment_kg": "2.5", **inventory})
        assert response.status_code == 302
    with app.app_context():
        assert {item.lift for item in MeetLift.query.filter_by(entry_id=entry_id, kind="warmup")} == {"squat", "bench", "deadlift"}
        assert MeetLift.query.filter_by(entry_id=entry_id, kind="attempt", sequence=1).count() == 3
