from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.meal_plan import MealPlanAssignment, MealPlanTemplate
from ..services.meal_plans import (
    DayMode, DraftStatus, FoodSnapshot, MacroTolerance, MacroTotals, Meal, MealItem,
    MealPlanDay, MealPlanDraft, PrescriptionSnapshot, PublishedAssignment,
    Substitution, WorkflowConflictError, _periods_overlap,
)


def _macros(value):
    return MacroTotals(*(Decimal(str(value.get(name, 0))) for name in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g")))


def _macros_json(value):
    return {name: str(getattr(value, name)) for name in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g")}


def _food(value):
    return FoodSnapshot(value["food_id"], value["name"], Decimal(value["reference_amount"]), value["unit"], _macros(value["macros"]), value["facts_revision"])


def _food_json(value):
    return {"food_id": value.food_id, "name": value.name, "reference_amount": str(value.reference_amount), "unit": value.unit, "macros": _macros_json(value.macros), "facts_revision": value.facts_revision}


def _item(value):
    return MealItem(value["item_id"], _food(value["food"]), Decimal(value["amount"]), value.get("note"))


def _item_json(value):
    return {"item_id": value.item_id, "food": _food_json(value.food), "amount": str(value.amount), "note": value.note}


def _days(value):
    return tuple(MealPlanDay(day["day_id"], day["name"], day["position"], DayMode(day["mode"]), tuple(Meal(meal["meal_id"], meal["name"], meal["position"], tuple(_item(item) for item in meal["items"]), meal.get("note")) for meal in day["meals"]), _macros(day.get("flexible_target", {})), day.get("note")) for day in value)


def _days_json(value):
    return [{"day_id": day.day_id, "name": day.name, "position": day.position, "mode": day.mode.value, "meals": [{"meal_id": meal.meal_id, "name": meal.name, "position": meal.position, "items": [_item_json(item) for item in meal.items], "note": meal.note} for meal in day.meals], "flexible_target": _macros_json(day.flexible_target), "note": day.note} for day in value]


def _subs(value):
    return tuple(Substitution(item["substitution_id"], item["target_item_id"], _item(item["replacement"]), item["label"]) for item in value)


def _subs_json(value):
    return [{"substitution_id": item.substitution_id, "target_item_id": item.target_item_id, "replacement": _item_json(item.replacement), "label": item.label} for item in value]


class SqlAlchemyMealPlanRepository:
    def get_draft(self, template_id):
        row = db.session.get(MealPlanTemplate, template_id)
        if row is None:
            return None
        return MealPlanDraft(row.id, row.revision, str(row.coach_id), row.name, _days(row.payload["days"]), _subs(row.payload.get("substitutions", [])), row.payload.get("notes"), DraftStatus(row.status))

    def list_drafts(self, coach_id=None):
        query = MealPlanTemplate.query
        if coach_id is not None:
            query = query.filter_by(coach_id=coach_id)
        return tuple(self.get_draft(row.id) for row in query.order_by(MealPlanTemplate.updated_at.desc()).all())

    def save_draft(self, draft, expected_revision=None):
        row = db.session.get(MealPlanTemplate, draft.template_id)
        if expected_revision is not None and (row is None or row.revision != expected_revision):
            raise WorkflowConflictError("draft revision is stale")
        if row is None:
            row = MealPlanTemplate(id=draft.template_id, coach_id=int(draft.coach_id))
            db.session.add(row)
        row.revision, row.status, row.name = draft.revision, draft.status.value, draft.name
        row.payload = {"days": _days_json(draft.days), "substitutions": _subs_json(draft.substitutions), "notes": draft.notes}
        db.session.flush()

    def add_assignment(self, assignment):
        existing = self.assignments_for(assignment.athlete_id)
        overlaps = [item for item in existing if _periods_overlap(item, assignment)]
        if any(item.effective_from >= assignment.effective_from for item in overlaps):
            raise WorkflowConflictError("assignment effective period overlaps")
        for item in overlaps:
            # Publishing a later revision supersedes the previous effective
            # period; its immutable content remains available in history.
            row = db.session.get(MealPlanAssignment, item.assignment_id)
            row.effective_until = assignment.effective_from - timedelta(days=1)
        snapshot = {"template_name": assignment.template_name, "days": _days_json(assignment.days), "substitutions": _subs_json(assignment.substitutions), "prescription": {"id": assignment.prescription.prescription_id, "revision": assignment.prescription.revision, "targets": _macros_json(assignment.prescription.targets)}, "publication_note": assignment.publication_note, "tolerance": _macros_json(assignment.tolerance)}
        db.session.add(MealPlanAssignment(id=assignment.assignment_id, athlete_id=assignment.athlete_id, template_id=assignment.template_id, template_revision=assignment.template_revision, effective_from=assignment.effective_from, effective_until=assignment.effective_until, published_by_user_id=int(assignment.published_by), published_at=assignment.published_at, snapshot=snapshot))
        try:
            db.session.flush()
        except IntegrityError as exc:
            raise WorkflowConflictError("assignment id already exists") from exc

    def assignments_for(self, athlete_id):
        rows = MealPlanAssignment.query.filter_by(athlete_id=athlete_id).order_by(MealPlanAssignment.effective_from.desc(), MealPlanAssignment.published_at.desc()).all()
        return tuple(self._assignment(row) for row in rows)

    def list_assignments(self, athlete_ids=None):
        query = MealPlanAssignment.query
        if athlete_ids is not None:
            if not athlete_ids:
                return ()
            query = query.filter(MealPlanAssignment.athlete_id.in_(athlete_ids))
        rows = query.order_by(MealPlanAssignment.published_at.desc()).all()
        return tuple(self._assignment(row) for row in rows)

    def get_assignment(self, assignment_id):
        row = db.session.get(MealPlanAssignment, assignment_id)
        return self._assignment(row) if row else None

    @staticmethod
    def _assignment(row):
        value = row.snapshot
        tolerance = MacroTolerance(**{name: Decimal(str(raw)) for name, raw in value.get("tolerance", {}).items()})
        prescription = value["prescription"]
        published_at = row.published_at.replace(tzinfo=UTC) if row.published_at.tzinfo is None else row.published_at
        return PublishedAssignment(row.id, row.athlete_id, row.template_id, row.template_revision, _days(value["days"]), _subs(value.get("substitutions", [])), PrescriptionSnapshot(prescription["id"], prescription["revision"], _macros(prescription["targets"])), row.effective_from, row.effective_until, str(row.published_by_user_id), published_at, value.get("publication_note"), tolerance, value.get("template_name"))
