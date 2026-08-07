from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models.athlete import Athlete
from .models.meet_day import LIFTS, OUTCOMES, Meet, MeetEntry, MeetLift
from .services.meet_day import build_board
from .services.plate_loading import (
    DEFAULT_PLATES_KG,
    DEFAULT_PLATE_INVENTORY,
    build_warmups,
    calculate_load,
)

meet_day_bp = Blueprint("meet_day", __name__, url_prefix="/meet-day")


def _render_index_error(message: str, form):
    return render_template(
        "meet_day/index.html",
        meets=Meet.query.order_by(Meet.meet_date.desc(), Meet.id.desc()).all(),
        today=datetime.now(UTC).date().isoformat(),
        athletes=Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all(),
        form=form,
        error=message,
    ), 400


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
        athletes=Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all(),
        form={},
    )


@meet_day_bp.post("")
def create():
    form = request.form
    name = request.form.get("name", "").strip()
    try:
        meet_date = date.fromisoformat(request.form.get("meet_date", ""))
    except ValueError:
        meet_date = None
    if not name or len(name) > 160 or meet_date is None:
        return _render_index_error("Enter a name and valid meet date.", form)
    try:
        notes = _optional_text(request.form.get("notes"), "Notes")
    except ValueError as exc:
        return _render_index_error(str(exc), form)
    try:
        bodyweight = _weight(form.get("bodyweight_kg"))
        federation = _optional_text(form.get("federation"), "Federation", 80)
        weight_class = _optional_text(form.get("weight_class"), "Weight class", 40)
        athlete_id = int(form.get("athlete_id")) if form.get("athlete_id") else None
    except (ValueError, TypeError) as exc:
        return _render_index_error(str(exc), form)
    athlete = db.session.get(Athlete, athlete_id) if athlete_id else None
    if athlete_id and athlete is None:
        abort(404)
    meet = Meet(
        name=name,
        meet_date=meet_date,
        notes=notes,
        federation=federation,
        bodyweight_kg=bodyweight,
        weight_class=weight_class,
    )
    db.session.add(meet)
    if athlete:
        db.session.add(MeetEntry(meet=meet, athlete=athlete, flight=1, platform_order=1))
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
        default_plates=DEFAULT_PLATES_KG,
        default_plate_inventory=DEFAULT_PLATE_INVENTORY,
        plate_result=None,
    )


def _inventory_from_form():
    inventory = {}
    for plate in DEFAULT_PLATES_KG:
        value = request.form.get(f"plate_{plate}", str(DEFAULT_PLATE_INVENTORY[plate]))
        try:
            count = int(value)
        except ValueError as exc:
            raise ValueError(
                "Plate inventory must use whole-number counts per side."
            ) from exc
        if count < 0 or count > 20:
            raise ValueError("Plate inventory must be between 0 and 20 per side.")
        inventory[plate] = count
    return inventory


@meet_day_bp.post("/<int:meet_id>/plate-calculator")
def plate_calculator(meet_id: int):
    meet = _meet(meet_id)
    try:
        bar_kg = request.form.get("custom_bar") or request.form.get("bar_kg", "20")
        result = calculate_load(
            request.form.get("target_kg", ""),
            bar_kg=bar_kg,
            collars_kg=request.form.get("collars_kg", "0"),
            inventory=_inventory_from_form(),
        )
    except ValueError as exc:
        result, error = None, str(exc)
    else:
        error = None
    return render_template(
        "meet_day/detail.html",
        board=build_board(meet),
        athletes=Athlete.query.order_by(Athlete.last_name, Athlete.first_name).all(),
        lifts=LIFTS,
        outcomes=OUTCOMES,
        default_plates=DEFAULT_PLATES_KG,
        default_plate_inventory=DEFAULT_PLATE_INVENTORY,
        plate_result=result,
        calculator_error=error,
    ), 400 if error else 200


@meet_day_bp.post("/<int:meet_id>/entries/<int:entry_id>/warmups")
def generate_warmups(meet_id: int, entry_id: int):
    meet = _meet(meet_id)
    entry = db.session.get(MeetEntry, entry_id)
    if entry is None or entry.meet_id != meet.id:
        abort(404)
    lift = request.form.get("lift", "")
    try:
        overrides = [
            value.strip()
            for value in request.form.get("manual_overrides", "").split(",")
            if value.strip()
        ]
        plan = build_warmups(
            lift,
            request.form.get("opener_kg", ""),
            bar_kg=request.form.get("bar_kg", "20"),
            collars_kg=request.form.get("collars_kg", "0"),
            first_loaded_kg=request.form.get("first_loaded_kg") or None,
            stages=(
                int(request.form["stages"])
                if request.form.get("stages")
                else None
            ),
            minimum_increment_kg=request.form.get("minimum_increment_kg", "2.5"),
            inventory=_inventory_from_form(),
            overrides_kg=overrides or None,
        )
    except (ValueError, KeyError) as exc:
        return str(exc), 400
    MeetLift.query.filter_by(entry_id=entry.id, lift=lift, kind="warmup").delete()
    for warmup in plan:
        kind = "attempt" if warmup.opener else "warmup"
        if kind == "attempt":
            existing = MeetLift.query.filter_by(
                entry_id=entry.id, lift=lift, kind="attempt", sequence=1
            ).one_or_none()
            if existing:
                existing.weight_kg = Decimal(warmup.weight_kg)
                existing.notes = "Opener"
                continue
        db.session.add(
            MeetLift(
                entry=entry,
                lift=lift,
                kind=kind,
                sequence=1 if kind == "attempt" else warmup.sequence,
                weight_kg=Decimal(warmup.weight_kg),
                notes=(
                    f"{warmup.repetitions} reps · {warmup.percentage}% · "
                    f"{warmup.loading.instruction}"
                ),
            )
        )
    db.session.commit()
    return redirect(url_for("meet_day.detail", meet_id=meet.id))


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
