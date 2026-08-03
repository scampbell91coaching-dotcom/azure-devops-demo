from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from ..models.checkins import AthleteCheckinSettings, WeeklyCheckin

SCORE_FIELDS = {
    "fatigue": "Fatigue",
    "recovery": "Readiness",
    "motivation": "Motivation",
    "sleep_quality": "Sleep quality",
    "stress": "Stress",
}
PERCENT_FIELDS = {
    "training_adherence": "Training adherence",
    "nutrition_adherence": "Nutrition adherence",
}
NON_NEGATIVE_FIELDS = {
    "average_bodyweight_kg": "Average bodyweight",
    "calories_average": "Average calories",
    "protein_average_g": "Average protein",
    "steps_average": "Average steps",
}


@dataclass
class CheckinSubmission:
    values: dict[str, object | None] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def athlete_checkins(athlete_id: int) -> list[WeeklyCheckin]:
    return (
        WeeklyCheckin.query.filter_by(athlete_id=athlete_id)
        .order_by(WeeklyCheckin.week_ending.desc(), WeeklyCheckin.submitted_at.desc())
        .all()
    )


def due_message(
    settings: AthleteCheckinSettings,
    on_date: date,
) -> str | None:
    if not settings.workflow_active or not settings.has_enabled_modules:
        return None

    week_start = on_date.fromordinal(on_date.toordinal() - on_date.weekday())
    due_date = week_start.fromordinal(week_start.toordinal() + settings.checkin_day)
    if on_date < due_date:
        return None

    week_end = week_start.fromordinal(week_start.toordinal() + 6)
    submitted = WeeklyCheckin.query.filter(
        WeeklyCheckin.athlete_id == settings.athlete_id,
        WeeklyCheckin.week_ending >= week_start,
        WeeklyCheckin.week_ending <= week_end,
    ).first()
    if submitted is not None:
        return None
    if on_date == due_date:
        return "Your weekly check-in is due today."
    return f"Your weekly check-in is overdue from {due_date:%A %d %B}."


def validate_submission(
    form: Mapping[str, str],
    settings: AthleteCheckinSettings,
) -> CheckinSubmission:
    result = CheckinSubmission()
    raw_week = form.get("week_ending", "").strip()
    try:
        result.values["week_ending"] = date.fromisoformat(raw_week)
    except ValueError:
        result.errors["week_ending"] = "Choose a valid week-ending date."

    if not settings.workflow_active or not settings.has_enabled_modules:
        result.errors["form"] = "Weekly check-ins are not currently enabled."

    active_scores = {"sleep_quality", "stress"}
    if settings.training_enabled:
        active_scores.update({"fatigue", "recovery", "motivation"})
    for name in active_scores:
        _parse_number(form, result, name, SCORE_FIELDS[name], minimum=1, maximum=10)

    if settings.training_enabled:
        _parse_number(
            form,
            result,
            "training_adherence",
            PERCENT_FIELDS["training_adherence"],
            minimum=0,
            maximum=100,
        )
    if settings.nutrition_enabled:
        _parse_number(
            form,
            result,
            "nutrition_adherence",
            PERCENT_FIELDS["nutrition_adherence"],
            minimum=0,
            maximum=100,
        )
        for name, label in NON_NEGATIVE_FIELDS.items():
            _parse_number(
                form,
                result,
                name,
                label,
                minimum=0,
                as_float=name == "average_bodyweight_kg",
            )

    if "week_ending" in result.values:
        duplicate = WeeklyCheckin.query.filter_by(
            athlete_id=settings.athlete_id,
            week_ending=result.values["week_ending"],
        ).first()
        if duplicate is not None:
            result.errors["week_ending"] = (
                "A check-in has already been submitted for this week."
            )
    return result


def _parse_number(
    form: Mapping[str, str],
    result: CheckinSubmission,
    name: str,
    label: str,
    *,
    minimum: int,
    maximum: int | None = None,
    as_float: bool = False,
) -> None:
    raw_value = form.get(name, "").strip()
    if not raw_value:
        result.values[name] = None
        return
    try:
        value = float(raw_value) if as_float else int(raw_value)
    except ValueError:
        result.errors[name] = f"{label} must be a number."
        return
    if value < minimum or (maximum is not None and value > maximum):
        expected = (
            f"between {minimum} and {maximum}" if maximum else f"{minimum} or more"
        )
        result.errors[name] = f"{label} must be {expected}."
        return
    result.values[name] = value
