from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import Blueprint, render_template, request

attempt_selection_bp = Blueprint(
    "attempt_selection", __name__, url_prefix="/attempt-selection"
)

VALID_LIFTS = {"squat", "bench", "deadlift"}
VALID_UNITS = {"kg", "lb"}


@attempt_selection_bp.app_template_filter("format_decimal")
def format_decimal(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".")


class AttemptSelectionError(ValueError):
    """Raised when an attempt recommendation cannot be safely produced."""


@dataclass(frozen=True)
class AttemptStrategy:
    opener_percent: Decimal = Decimal(90)
    second_percent: Decimal = Decimal(95)
    third_percent: Decimal = Decimal(100)
    rounding_increment: Decimal = Decimal("2.5")


@dataclass(frozen=True)
class AttemptRecommendation:
    lift: str
    unit: str
    reference_load: Decimal
    attempts: tuple[Decimal, Decimal, Decimal]
    strategy: AttemptStrategy
    manual_override: bool


def _decimal(value: object, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise AttemptSelectionError(f"{label} must be a number.") from None
    if not number.is_finite():
        raise AttemptSelectionError(f"{label} must be a finite number.")
    return number


def _positive(value: object, label: str) -> Decimal:
    number = _decimal(value, label)
    if number <= 0:
        raise AttemptSelectionError(f"{label} must be greater than zero.")
    return number


def _round_to_increment(load: Decimal, increment: Decimal) -> Decimal:
    return (load / increment).quantize(Decimal(1), rounding=ROUND_HALF_UP) * increment


def recommend_attempts(
    *,
    lift: str,
    unit: str,
    reference_load: object,
    strategy: AttemptStrategy | None = None,
    manual_attempts: tuple[object, object, object] | None = None,
) -> AttemptRecommendation:
    """Recommend three meet attempts, or validate and preserve a coach override."""
    normalized_lift = lift.strip().lower()
    normalized_unit = unit.strip().lower()
    if normalized_lift not in VALID_LIFTS:
        raise AttemptSelectionError("Lift must be squat, bench, or deadlift.")
    if normalized_unit not in VALID_UNITS:
        raise AttemptSelectionError("Units must be kg or lb.")

    reference = _positive(reference_load, "Reference load")
    selected = strategy or AttemptStrategy()
    percentages = (
        _positive(selected.opener_percent, "Opener percentage"),
        _positive(selected.second_percent, "Second percentage"),
        _positive(selected.third_percent, "Third percentage"),
    )
    if not percentages[0] < percentages[1] < percentages[2]:
        raise AttemptSelectionError(
            "Attempt percentages must increase from opener to third."
        )
    increment = _positive(selected.rounding_increment, "Rounding increment")
    selected = AttemptStrategy(*percentages, rounding_increment=increment)

    if manual_attempts is not None:
        attempts = tuple(
            _positive(value, f"{label} attempt")
            for value, label in zip(
                manual_attempts, ("Opener", "Second", "Third"), strict=True
            )
        )
    else:
        attempts = tuple(
            _round_to_increment(reference * percent / Decimal(100), increment)
            for percent in percentages
        )

    if not attempts[0] < attempts[1] < attempts[2]:
        detail = (
            "Manual attempts" if manual_attempts is not None else "Rounded attempts"
        )
        raise AttemptSelectionError(f"{detail} must increase from opener to third.")

    return AttemptRecommendation(
        lift=normalized_lift,
        unit=normalized_unit,
        reference_load=reference,
        attempts=attempts,  # type: ignore[arg-type]
        strategy=selected,
        manual_override=manual_attempts is not None,
    )


def _form_strategy() -> AttemptStrategy:
    return AttemptStrategy(
        opener_percent=request.form.get("opener_percent", "90"),  # type: ignore[arg-type]
        second_percent=request.form.get("second_percent", "95"),  # type: ignore[arg-type]
        third_percent=request.form.get("third_percent", "100"),  # type: ignore[arg-type]
        rounding_increment=request.form.get("rounding_increment", "2.5"),  # type: ignore[arg-type]
    )


@attempt_selection_bp.route("/", methods=["GET", "POST"])
def index() -> str:
    form = request.form if request.method == "POST" else {}
    recommendation = None
    error = None
    if request.method == "POST":
        manual_values = tuple(
            request.form.get(f"manual_{number}", "").strip() for number in range(1, 4)
        )
        try:
            if any(manual_values) and not all(manual_values):
                raise AttemptSelectionError(
                    "Enter all three manual attempts or leave all three blank."
                )
            recommendation = recommend_attempts(
                lift=request.form.get("lift", ""),
                unit=request.form.get("unit", ""),
                reference_load=request.form.get("reference_load", ""),
                strategy=_form_strategy(),
                manual_attempts=manual_values if all(manual_values) else None,
            )
        except AttemptSelectionError as exc:
            error = str(exc)
    return render_template(
        "attempt_selection/index.html",
        coach_section="attempt_selection",
        form=form,
        recommendation=recommendation,
        error=error,
    )


__all__ = [
    "AttemptRecommendation",
    "AttemptSelectionError",
    "AttemptStrategy",
    "attempt_selection_bp",
    "recommend_attempts",
]
