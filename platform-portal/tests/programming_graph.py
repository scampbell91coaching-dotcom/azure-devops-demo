"""Canonical, ID-free programme graphs used by refactor characterization tests."""

from __future__ import annotations

from typing import Any


def normalize_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Serialize a stored factory proposal without unstable database identity."""
    factory = payload["factory"]
    days = []
    for day in payload["preview"]:
        exposures = list(day.get("exposures", ()))
        accessory_by_name = {item["name"]: item for item in day.get("accessories", ())}
        prescriptions = []
        for position, name in enumerate(day["exercises"], 1):
            if position <= int(day["main_count"]):
                intent = exposures[position - 1]
                prescriptions.append({
                    "position": position,
                    "exercise_name": name,
                    "lift_family": intent["lift_family"],
                    "exposure_role": intent["legacy_role"],
                    "sets": intent["sets"],
                    "reps": str(intent["reps"]),
                    "rpe": None,
                    "rpe_offset": float(intent["rpe_offset"]),
                    "provenance": intent.get("exercise_provenance"),
                    "notes": intent.get("reason"),
                    "accessory_prescriptions": None,
                })
            else:
                accessory = accessory_by_name[name]
                prescriptions.append({
                    "position": position,
                    "exercise_name": name,
                    "lift_family": None,
                    "exposure_role": None,
                    "sets": None,
                    "reps": None,
                    "rpe": None,
                    "rpe_offset": None,
                    "provenance": accessory.get("provenance"),
                    "notes": accessory.get("reason"),
                    "accessory_prescriptions": accessory.get("prescriptions"),
                })
        days.append({
            "position": int(day["day"]),
            "day_label": f"Day {day['day']}",
            "day_type": day["day_type"],
            "prescriptions": prescriptions,
        })
    return {
        "source": "preview",
        "generator_version": payload.get("generator_version"),
        "block": {"name": factory["name"], "week_count": int(factory["week_count"])},
        "days": days,
    }


def normalize_persisted(block: Any) -> dict[str, Any]:
    """Serialize the durable graph, preserving authored order and values."""
    weeks = []
    for week in sorted(block.weeks, key=lambda row: (row.position, row.id or 0)):
        sessions = []
        for session in sorted(week.sessions, key=lambda row: (row.position, row.id or 0)):
            slots = {row.id: row for row in session.lift_slots}
            sessions.append({
                "position": session.position,
                "name": session.name,
                "day_label": session.day_label,
                "notes": session.notes,
                "prescriptions": [{
                    "position": row.position,
                    "exercise_name": row.exercise_name,
                    "lift_family": slots[row.lift_slot_id].lift_family if row.lift_slot_id else None,
                    "exposure_role": slots[row.lift_slot_id].exposure_role if row.lift_slot_id else None,
                    "slot_position": slots[row.lift_slot_id].position if row.lift_slot_id else None,
                    "slot_role": row.slot_role,
                    "sets": row.sets,
                    "reps": row.reps,
                    "rpe": row.rpe,
                    "provenance": row.provenance,
                    "notes": row.notes,
                    "rest_seconds": row.rest_seconds,
                } for row in sorted(session.prescriptions, key=lambda item: (item.position, item.id or 0))],
            })
        weeks.append({"position": week.position, "name": week.name, "notes": week.notes, "sessions": sessions})
    return {
        "source": "persisted",
        "block": {"name": block.name, "objective": block.objective, "status": block.status},
        "weeks": weeks,
    }


def normalize_persisted_programme(block: Any) -> dict[str, Any]:
    """Serialize the durable graph in the signed proposal's exact schema."""
    return {
        "schema_version": 1,
        "block": {"name": block.name, "objective": block.objective, "status": block.status},
        "weeks": [{
            "name": week.name, "position": week.position, "notes": week.notes,
            "sessions": [{
                "name": session.name, "day_label": session.day_label,
                "day_type": session.name.rsplit("·", 1)[1].strip(),
                "position": session.position, "notes": session.notes,
                "warmups": ["session-general"] + [
                    slot.lift_family
                    for slot in sorted(
                        session.lift_slots, key=lambda row: (row.position, row.id or 0)
                    )
                ],
                "prescriptions": [{
                    "exercise_id": item.exercise_id,
                    "exercise_name": item.exercise_name,
                    "position": item.position,
                    "sets": item.sets,
                    "reps": item.reps,
                    "prescription_type": item.prescription_type,
                    "rpe": item.rpe,
                    "rest_seconds": item.rest_seconds,
                    "notes": item.notes,
                    "provenance": item.provenance,
                    "slot_role": item.slot_role,
                    "lift_slot": ({
                        "position": item.lift_slot.position,
                        "lift_family": item.lift_slot.lift_family,
                        "exposure_role": item.lift_slot.exposure_role,
                    } if item.lift_slot else None),
                } for item in sorted(
                    session.prescriptions, key=lambda row: (row.position, row.id or 0)
                )],
            } for session in sorted(
                week.sessions, key=lambda row: (row.position, row.id or 0)
            )],
        } for week in sorted(block.weeks, key=lambda row: (row.position, row.id or 0))],
    }
