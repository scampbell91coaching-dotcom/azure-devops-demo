from datetime import date
from decimal import Decimal

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import WeeklyCheckin
from portal.models.meet_day import Meet, MeetEntry
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.services.competition_bodyweight import build_bodyweight_planning_context


@pytest.fixture()
def app():
    instance = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with instance.app_context():
        db.create_all()
    return instance


def athlete(**values):
    item = Athlete(first_name="Alex", last_name="Lifter", email="alex@planning.test", **values)
    db.session.add(item)
    db.session.flush()
    return item


def test_structured_upcoming_meet_wins_over_legacy_competition_text(app):
    with app.app_context():
        item = athlete(next_competition="Autumn Open", weight_class="83 kg")
        later = Meet(name="Nationals", meet_date=date(2026, 12, 1))
        sooner = Meet(name="Regional", meet_date=date(2026, 10, 3))
        db.session.add_all([MeetEntry(meet=later, athlete=item), MeetEntry(meet=sooner, athlete=item)])
        db.session.commit()

        result = build_bodyweight_planning_context(item, as_of=date(2026, 8, 11))

        assert result.competition.name == "Regional"
        assert result.competition.source == "meet_entry"
        assert result.competition.days_away == 53


def test_latest_dated_bodyweight_is_used_with_provenance_and_future_data_excluded(app):
    with app.app_context():
        item = athlete(bodyweight_kg=90)
        db.session.add_all([
            WeeklyCheckin(athlete=item, week_ending=date(2026, 8, 1), average_bodyweight_kg=89.4),
            NutritionCheckIn(athlete=item, checkin_date=date(2026, 8, 8), bodyweight_kg=88.9,
                             nutrition_adherence=7, hunger=5, energy=7, sleep_quality=7,
                             stress=4, digestion=7, training_performance=8),
            WeeklyCheckin(athlete=item, week_ending=date(2026, 8, 20), average_bodyweight_kg=70),
        ])
        db.session.commit()

        result = build_bodyweight_planning_context(item, as_of=date(2026, 8, 11))

        assert result.latest.bodyweight_kg == Decimal("88.90")
        assert result.latest.source == "nutrition_checkin"
        assert len(result.recent) == 2


def test_explicit_target_produces_transparent_math_without_persisting(app):
    with app.app_context():
        item = athlete(bodyweight_kg=90, weight_class="83 kg", next_competition="2026-10-06")
        db.session.commit()

        result = build_bodyweight_planning_context(
            item, as_of=date(2026, 8, 11), target_bodyweight_kg="86"
        )

        assert result.change_required_kg == Decimal("-4.00")
        assert result.weeks_available == Decimal("8.00")
        assert result.required_change_per_week_kg == Decimal("-0.50")
        assert "Coach review is required" in result.prompts[-1]
        assert item.bodyweight_kg == 90


def test_weight_class_is_never_invented_as_bodyweight_target(app):
    with app.app_context():
        item = athlete(bodyweight_kg=84, weight_class="Under 83", next_competition="Autumn Open")
        db.session.commit()

        result = build_bodyweight_planning_context(item, as_of=date(2026, 8, 11))

        assert result.target_bodyweight_kg is None
        assert result.change_required_kg is None
        assert result.competition.competition_date is None
        assert "Set an explicit target bodyweight" in " ".join(result.prompts)


@pytest.mark.parametrize("target", [0, -1, "nan", "not-a-number"])
def test_invalid_targets_are_rejected(app, target):
    with app.app_context():
        item = athlete()
        with pytest.raises(ValueError):
            build_bodyweight_planning_context(item, as_of=date(2026, 8, 11), target_bodyweight_kg=target)
