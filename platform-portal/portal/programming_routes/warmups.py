import re

from flask import Blueprint, abort, flash, g, redirect, request, url_for

from ..extensions import db
from ..models.athlete_state import AthleteStateOverride
from ..models.programming import ProgrammingLiftSlot, TrainingSession
from ..models.warmup import WarmupAssignment, WarmupOverride, WarmupPlanSnapshot, WarmupProtocol, WarmupProtocolStep
from ..services.movement_warmup_candidates import find_candidate
from ..programming_services.revisions import append_revision
from ..tenancy import require_programming_access

PHASES = {"general": 10, "athlete": 20, "lift": 30, "barbell": 40}


def _session(session_id: int) -> TrainingSession:
    item = db.session.get(TrainingSession, session_id)
    if item is None:
        abort(404)
    require_programming_access(item)
    if WarmupPlanSnapshot.query.filter_by(athlete_id=item.week.block.athlete_id, session_id=item.id).first():
        abort(409, description="The athlete has opened this session; its warm-up history is locked.")
    return item


def _actor_id():
    return getattr(g.get("current_user"), "id", None)


def _target_slot(session: TrainingSession) -> ProgrammingLiftSlot | None:
    slot_id = request.form.get("lift_slot_id", type=int)
    if slot_id is None:
        return None
    slot = db.session.get(ProgrammingLiftSlot, slot_id)
    if slot is None or slot.session_id != session.id:
        abort(400, description="Warm-up lift slot must belong to this session.")
    return slot


def register_warmup_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/sessions/<int:session_id>/warmup-protocols")
    def create_warmup_protocol(session_id: int):
        session = _session(session_id)
        name = request.form.get("name", "").strip()
        reason = request.form.get("reason", "").strip()
        raw_steps = request.form.get("steps", "")
        lift_slot = _target_slot(session)
        if not name or not reason:
            abort(400, description="Plan name and assignment reason are required.")
        stable_key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:80]
        version = (db.session.query(db.func.max(WarmupProtocol.version)).filter_by(stable_key=stable_key).scalar() or 0) + 1
        protocol = WarmupProtocol(stable_key=stable_key, version=version, name=name, created_by_user_id=_actor_id())
        try:
            for position, line in enumerate((line.strip() for line in raw_steps.splitlines() if line.strip()), 1):
                parts = [part.strip() for part in line.split("|")]
                if len(parts) < 4 or parts[0].casefold() not in PHASES or parts[2].casefold() not in {"reps", "duration", "barbell"}:
                    raise ValueError
                phase, step_name, kind, value = parts[:4]
                sets = int(parts[4]) if len(parts) > 4 and parts[4] else 1
                rest = int(parts[5]) if len(parts) > 5 and parts[5] else None
                notes = parts[6] if len(parts) > 6 and parts[6] else None
                kwargs = {"reps": None, "duration_seconds": None, "percentage": None, "load_kg": None}
                if kind.casefold() == "duration": kwargs["duration_seconds"] = int(value)
                elif kind.casefold() == "barbell":
                    kwargs["reps"] = int(value.split("@")[0])
                    target = value.split("@", 1)[1]
                    kwargs["percentage" if target.endswith("%") else "load_kg"] = float(target.rstrip("%kg "))
                else: kwargs["reps"] = int(value)
                protocol.steps.append(WarmupProtocolStep(position=position, phase=PHASES[phase.casefold()], name=step_name, kind=kind.casefold(), sets=sets, rest_seconds=rest, notes=notes, **kwargs))
        except (ValueError, IndexError):
            abort(400, description="Each step must use phase | name | reps/duration/barbell | value [| sets | rest | notes].")
        if not protocol.steps:
            abort(400, description="Add at least one warm-up step.")
        db.session.add(protocol)
        db.session.flush()
        db.session.add(WarmupAssignment(protocol_id=protocol.id, athlete_id=session.week.block.athlete_id, session_id=session.id, lift_slot_id=lift_slot.id if lift_slot else None, assigned_by_user_id=_actor_id(), reason=reason))
        append_revision(session.week.block, change_type="warmup_created", summary=f'Created and assigned warm-up "{name}"', reason=reason)
        db.session.commit()
        flash("Reusable warm-up created and assigned.", "success")
        return redirect(url_for("programming.session", session_id=session.id))

    @blueprint.post("/programming/sessions/<int:session_id>/warmup-assignments")
    def assign_warmup(session_id: int):
        session = _session(session_id)
        protocol = db.session.get(WarmupProtocol, request.form.get("protocol_id", type=int))
        reason = request.form.get("reason", "").strip()
        lift_slot = _target_slot(session)
        if protocol is None or not reason:
            abort(400, description="Protocol and assignment reason are required.")
        db.session.add(WarmupAssignment(protocol_id=protocol.id, athlete_id=session.week.block.athlete_id, session_id=session.id, lift_slot_id=lift_slot.id if lift_slot else None, assigned_by_user_id=_actor_id(), reason=reason))
        append_revision(session.week.block, change_type="warmup_assigned", summary=f'Assigned warm-up "{protocol.name}"', reason=reason)
        db.session.commit()
        return redirect(url_for("programming.session", session_id=session.id))

    @blueprint.post("/programming/sessions/<int:session_id>/warmup-candidates/accept")
    def accept_warmup_candidate(session_id: int):
        session = _session(session_id)
        athlete_id = session.week.block.athlete_id
        candidate = find_candidate(
            athlete_id, session, request.form.get("protocol_id", type=int)
        )
        if candidate is None:
            abort(409, description="This warm-up candidate is no longer applicable.")
        reason = candidate.assignment_reason()
        if len(reason) > 500:
            abort(409, description="Candidate provenance exceeds assignment storage.")
        db.session.add(
            WarmupAssignment(
                protocol_id=candidate.protocol_id,
                athlete_id=athlete_id,
                session_id=session.id,
                assigned_by_user_id=_actor_id(),
                reason=reason,
            )
        )
        append_revision(session.week.block, change_type="warmup_candidate_accepted", summary="Accepted warm-up candidate", reason=reason)
        db.session.commit()
        flash("Coach accepted the warm-up candidate.", "success")
        return redirect(url_for("programming.session", session_id=session.id))

    @blueprint.post("/programming/sessions/<int:session_id>/warmup-candidates/override")
    def override_warmup_candidate(session_id: int):
        """Remove or explain a coach replacement for a current suggestion."""
        session = _session(session_id)
        athlete_id = session.week.block.athlete_id
        candidate = find_candidate(
            athlete_id, session, request.form.get("protocol_id", type=int)
        )
        action = request.form.get("action")
        reason = request.form.get("reason", "").strip()
        replacement = request.form.get("replacement", "").strip()
        if candidate is None:
            abort(409, description="This warm-up candidate is no longer applicable.")
        if action not in {"remove", "override"} or not reason:
            abort(400, description="A valid action and coach reason are required.")
        if action == "override" and not replacement:
            abort(400, description="Replacement guidance is required for an override.")
        payload = {"action": action}
        if replacement:
            payload["recommendation"] = replacement
        db.session.add(
            AthleteStateOverride(
                athlete_id=athlete_id,
                target_type="warmup_selection_rule",
                target_ref=candidate.rule_id,
                override_json=payload,
                reason=reason,
                recorded_by=str(_actor_id() or "coach"),
            )
        )
        append_revision(
            session.week.block,
            change_type="warmup_candidate_overridden",
            summary=f"{action.title()}d warm-up candidate",
            reason=reason,
        )
        db.session.commit()
        flash("Warm-up candidate decision saved.", "success")
        return redirect(url_for("programming.session", session_id=session.id))

    @blueprint.post("/programming/sessions/<int:session_id>/warmup-overrides")
    def override_warmup(session_id: int):
        session = _session(session_id)
        reason = request.form.get("reason", "").strip()
        if not reason:
            abort(400, description="An override reason is required.")
        action = request.form.get("action")
        values = dict(athlete_id=session.week.block.athlete_id, session_id=session.id, action=action, reason=reason, created_by_user_id=_actor_id())
        if action == "remove":
            target = request.form.get("target_key", "").strip()
            if not target: abort(400)
            values["target_key"] = target
        elif action == "append":
            kind = request.form.get("kind", "reps")
            name = request.form.get("name", "").strip()
            if not name or kind not in {"reps", "duration"}: abort(400)
            values.update(phase=int(request.form.get("phase", 20)), name=name, kind=kind, sets=int(request.form.get("sets", 1)), reps=int(request.form["value"]) if kind == "reps" else None, duration_seconds=int(request.form["value"]) if kind == "duration" else None, rest_seconds=request.form.get("rest_seconds", type=int), notes=request.form.get("notes", "").strip() or None)
        else: abort(400)
        db.session.add(WarmupOverride(**values))
        append_revision(session.week.block, change_type="warmup_overridden", summary="Saved manual warm-up override", reason=reason)
        db.session.commit()
        flash("Manual warm-up override saved.", "success")
        return redirect(url_for("programming.session", session_id=session.id))
