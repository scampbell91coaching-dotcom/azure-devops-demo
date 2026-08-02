from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from .extensions import db
from .models.athlete import Athlete
from .models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from .programming_templates import day_templates

programming_bp = Blueprint("programming", __name__)


def _float(value: str | None) -> float | None:
    return float(value) if value and value.strip() else None


def _int(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


@programming_bp.get("/athletes/<int:athlete_id>/programming")
def athlete_program(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    blocks = (
        TrainingBlock.query.filter_by(athlete_id=athlete.id)
        .order_by(TrainingBlock.id.desc())
        .all()
    )

    return render_template(
        "programming/athlete_program.html",
        athlete=athlete,
        blocks=blocks,
    )


@programming_bp.get("/programming")
def index():
    athletes = Athlete.query.order_by(Athlete.last_name.asc()).all()
    blocks = TrainingBlock.query.order_by(TrainingBlock.id.desc()).all()
    return render_template("programming/index.html", athletes=athletes, blocks=blocks)


@programming_bp.post("/programming/blocks")
def create_block():
    athlete_id = request.form.get("athlete_id", type=int)
    name = request.form.get("name", "").strip()
    athlete = db.session.get(Athlete, athlete_id) if athlete_id else None
    if athlete is None or not name:
        abort(400)
    block = TrainingBlock(
        athlete=athlete,
        name=name,
        objective=request.form.get("objective", "").strip() or None,
    )
    db.session.add(block)
    db.session.commit()
    return redirect(url_for("programming.block", block_id=block.id))


@programming_bp.get("/programming/blocks/<int:block_id>")
def block(block_id: int):
    item = db.session.get(TrainingBlock, block_id)
    if item is None:
        abort(404)
    return render_template("programming/block.html", block=item)


@programming_bp.post("/programming/blocks/<int:block_id>/weeks")
def create_week(block_id: int):
    block = db.session.get(TrainingBlock, block_id)
    if block is None:
        abort(404)
    position = len(block.weeks) + 1
    week = TrainingWeek(
        block=block,
        name=request.form.get("name", "").strip() or f"Week {position}",
        position=position,
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.add(week)
    db.session.commit()
    return redirect(url_for("programming.week", week_id=week.id))


@programming_bp.get("/programming/weeks/<int:week_id>")
def week(week_id: int):
    item = db.session.get(TrainingWeek, week_id)
    if item is None:
        abort(404)
    return render_template("programming/week.html", week=item)


@programming_bp.post("/programming/weeks/<int:week_id>/sessions")
def create_session(week_id: int):
    week = db.session.get(TrainingWeek, week_id)
    if week is None:
        abort(404)
    position = len(week.sessions) + 1
    session = TrainingSession(
        week=week,
        name=request.form.get("name", "").strip() or f"Session {position}",
        day_label=request.form.get("day_label", "").strip() or None,
        position=position,
    )
    db.session.add(session)
    db.session.commit()
    return redirect(url_for("programming.session", session_id=session.id))


@programming_bp.get("/programming/sessions/<int:session_id>")
def session(session_id: int):
    item = db.session.get(TrainingSession, session_id)
    if item is None:
        abort(404)
    week = item.week
    block = week.block

    return render_template(
        "programming/session.html",
        session=item,
        week=week,
        block=block,
        day_templates=day_templates(),
    )


@programming_bp.post("/programming/sessions/<int:session_id>/prescriptions")
def create_prescription(session_id: int):
    session = db.session.get(TrainingSession, session_id)
    if session is None:
        abort(404)
    name = request.form.get("exercise_name", "").strip()
    if not name:
        abort(400)
    item = ExercisePrescription(
        session=session,
        exercise_name=name,
        position=len(session.prescriptions) + 1,
        sets=_int(request.form.get("sets")),
        reps=request.form.get("reps", "").strip() or None,
        load_kg=_float(request.form.get("load_kg")),
        percentage=_float(request.form.get("percentage")),
        rpe=_float(request.form.get("rpe")),
        tempo=request.form.get("tempo", "").strip() or None,
        rest_seconds=_int(request.form.get("rest_seconds")),
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("programming.session", session_id=session.id))


@programming_bp.post("/programming/sessions/<int:session_id>/duplicate")
def duplicate_session(session_id: int):
    source = db.session.get(TrainingSession, session_id)
    if source is None:
        abort(404)
    target = TrainingSession(
        week=source.week,
        name=f"{source.name} Copy",
        day_label=source.day_label,
        position=len(source.week.sessions) + 1,
        notes=source.notes,
    )
    db.session.add(target)
    db.session.flush()
    for item in source.prescriptions:
        db.session.add(
            ExercisePrescription(
                session=target,
                exercise_name=item.exercise_name,
                position=item.position,
                sets=item.sets,
                reps=item.reps,
                load_kg=item.load_kg,
                percentage=item.percentage,
                rpe=item.rpe,
                tempo=item.tempo,
                rest_seconds=item.rest_seconds,
                notes=item.notes,
            )
        )
    db.session.commit()
    return redirect(url_for("programming.session", session_id=target.id))


@programming_bp.post("/programming/weeks/<int:week_id>/duplicate")
def duplicate_week(week_id: int):
    source = db.session.get(TrainingWeek, week_id)
    if source is None:
        abort(404)
    target = TrainingWeek(
        block=source.block,
        name=f"{source.name} Copy",
        position=len(source.block.weeks) + 1,
        notes=source.notes,
    )
    db.session.add(target)
    db.session.flush()
    for source_session in source.sessions:
        target_session = TrainingSession(
            week=target,
            name=source_session.name,
            day_label=source_session.day_label,
            position=source_session.position,
            notes=source_session.notes,
        )
        db.session.add(target_session)
        db.session.flush()
        for item in source_session.prescriptions:
            db.session.add(
                ExercisePrescription(
                    session=target_session,
                    exercise_name=item.exercise_name,
                    position=item.position,
                    sets=item.sets,
                    reps=item.reps,
                    load_kg=item.load_kg,
                    percentage=item.percentage,
                    rpe=item.rpe,
                    tempo=item.tempo,
                    rest_seconds=item.rest_seconds,
                    notes=item.notes,
                )
            )
    db.session.commit()
    return redirect(url_for("programming.week", week_id=target.id))
