from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models.athlete import Athlete
from .models.meet_day import LIFTS, OUTCOMES, Meet, MeetEntry, MeetLift
from .services.meet_day import build_board

meet_day_bp = Blueprint("meet_day", __name__, url_prefix="/meet-day")


def _optional_text(value: str | None, field: str, limit: int = 2000) -> str | None:
    cleaned = (value or "").strip()
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be {limit} characters or fewer.")
    return cleaned or None


def _positive_int(value: str | None, field: str) -> int:
    try:
        parsed = int(value or "")
    except ValueError as exc:
        raise ValueError(f"{field} must be a whole number.") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be at least 1.")
    return parsed


def _weight(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Weight must be a number.") from exc
    if not parsed.is_finite() or parsed <= 0 or parsed > Decimal("9999.99"):
        raise ValueError("Weight must be between 0 and 9999.99 kg.")
    return parsed.quantize(Decimal("0.01"))


def _meet(meet_id: int) -> Meet:
    meet = db.session.get(Meet, meet_id)
    if meet is None:
        abort(404)
    return meet


@meet_day_bp.get("")
def index():
    meets = Meet.query.order_by(Meet.meet_date.desc(), Meet.id.desc()).all()
    return render_template(
        "meet_day/index.html",
        meets=meets,
        today=datetime.now(UTC).date().isoformat(),
    )


@meet_day_bp.post("")
def create():
    name = request.form.get("name", "").strip()
    try:
        meet_date = date.fromisoformat(request.form.get("meet_date", ""))
    except ValueError:
        meet_date = None
    if not name or len(name) > 160 or meet_date is None:
        return render_template(
            "meet_day/index.html",
            meets=Meet.query.all(),
            today=datetime.now(UTC).date().isoformat(),
            error="Enter a name and valid meet date.",
        ), 400
    try:
        notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return str(exc), 400
    meet = Meet(name=name, meet_date=meet_date, notes=notes)
    db.session.add(meet)
    db.session.commit()
    return redirect(url_for("meet_day.detail", meet_id=meet.id))


@meet_day_bp.get("/<int:meet_id>")
def detail(meet_id: int):
    meet = _meet(meet_id)
    athletes = Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all()
    return render_template(
        "meet_day/detail.html",
        board=build_board(meet),
        athletes=athletes,
        lifts=LIFTS,
        outcomes=OUTCOMES,
    )


@meet_day_bp.post("/<int:meet_id>/entries")
def add_entry(meet_id: int):
    meet = _meet(meet_id)
    try:
        athlete_id = _positive_int(request.form.get("athlete_id"), "Athlete")
        flight = _positive_int(request.form.get("flight"), "Flight")
        platform_order = _positive_int(request.form.get("platform_order"), "Order")
    except ValueError as exc:
        return str(exc), 400
    if db.session.get(Athlete, athlete_id) is None:
        abort(404)
    try:
        notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return str(exc), 400
    entry = MeetEntry(
        meet=meet,
        athlete_id=athlete_id,
        flight=flight,
        platform_order=platform_order,
        notes=notes,
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "Athlete is already entered in this meet.", 409
    return redirect(url_for("meet_day.detail", meet_id=meet.id))


@meet_day_bp.post("/<int:meet_id>/entries/<int:entry_id>")
def update_entry(meet_id: int, entry_id: int):
    meet = _meet(meet_id)
    entry = db.session.get(MeetEntry, entry_id)
    if entry is None or entry.meet_id != meet.id:
        abort(404)
    try:
        entry.flight = _positive_int(request.form.get("flight"), "Flight")
        entry.platform_order = _positive_int(
            request.form.get("platform_order"), "Order"
        )
    except ValueError as exc:
        return str(exc), 400
    try:
        entry.notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return str(exc), 400
    db.session.commit()
    return redirect(url_for("meet_day.detail", meet_id=meet.id))


@meet_day_bp.post("/<int:meet_id>/entries/<int:entry_id>/lifts")
def add_lift(meet_id: int, entry_id: int):
    meet = _meet(meet_id)
    entry = db.session.get(MeetEntry, entry_id)
    if entry is None or entry.meet_id != meet.id:
        abort(404)
    lift = request.form.get("lift", "")
    kind = request.form.get("kind", "")
    outcome = request.form.get("outcome", "pending")
    if (
        lift not in LIFTS
        or kind not in {"warmup", "attempt"}
        or outcome not in OUTCOMES
    ):
        return "Invalid lift, type, or outcome.", 400
    try:
        sequence = _positive_int(request.form.get("sequence"), "Sequence")
        weight = _weight(request.form.get("weight_kg"))
    except ValueError as exc:
        return str(exc), 400
    if kind == "attempt" and sequence > 3:
        return "Attempt number must be between 1 and 3.", 400
    try:
        notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return str(exc), 400
    item = MeetLift(
        entry=entry,
        lift=lift,
        kind=kind,
        sequence=sequence,
        weight_kg=weight,
        outcome=outcome,
        notes=notes,
    )
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "That lift slot already exists.", 409
    return redirect(url_for("meet_day.detail", meet_id=meet.id))


@meet_day_bp.post("/<int:meet_id>/lifts/<int:lift_id>")
def update_lift(meet_id: int, lift_id: int):
    meet = _meet(meet_id)
    item = db.session.get(MeetLift, lift_id)
    if item is None or item.entry.meet_id != meet.id:
        abort(404)
    outcome = request.form.get("outcome", "")
    if outcome not in OUTCOMES:
        return "Invalid outcome.", 400
    try:
        weight = _weight(request.form.get("weight_kg"))
    except ValueError as exc:
        return str(exc), 400
    item.weight_kg = weight
    item.outcome = outcome
    try:
        item.notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return str(exc), 400
    db.session.commit()
    return redirect(url_for("meet_day.detail", meet_id=meet.id))
