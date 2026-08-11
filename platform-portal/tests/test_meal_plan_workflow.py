from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from portal.services.meal_plans import (
    DayMode, DraftStatus, FoodSnapshot, InMemoryMealPlanRepository, MacroTotals,
    Meal, MealItem, MealPlanDay, MealPlanDraft, MealPlanWorkflow,
    PrescriptionSnapshot, PublicationError, Substitution, WorkflowConflictError,
)


def plan():
    food = FoodSnapshot("rice", "Rice", Decimal("100"), "g", MacroTotals(2000, 150, 250, 60, 25), "label-8")
    day = MealPlanDay("training", "Training", 1, DayMode.FIXED, (Meal("meal", "Main meal", 1, (MealItem("rice-slot", food, Decimal("100")),), "Eat after training"),), note="Training day")
    return MealPlanDraft("template-1", 1, "coach-1", "Performance plan", (day,), notes="Hydrate")


def prescription():
    return PrescriptionSnapshot("macro-9", 4, MacroTotals(2000, 150, 250, 60, 25))


def test_draft_editor_revises_portions_notes_and_whitelisted_substitutions():
    workflow = MealPlanWorkflow(InMemoryMealPlanRepository(), lambda _: True)
    potato = FoodSnapshot("potato", "Potato", Decimal("100"), "g", MacroTotals(2000, 150, 250, 60, 25), "facts-2")
    revised = workflow.set_portion(plan(), "rice-slot", "125")
    revised = workflow.set_notes(revised, "New coach note")
    revised = workflow.add_substitution(revised, Substitution("swap-1", "rice-slot", MealItem("potato-slot", potato, Decimal("100")), "Potato"))

    assert revised.revision == 4
    assert revised.days[0].meals[0].items[0].amount == Decimal("125")
    assert revised.substitutions[0].replacement.food.facts_revision == "facts-2"


def test_publication_freezes_template_food_and_prescription_revisions():
    repository = InMemoryMealPlanRepository()
    workflow = MealPlanWorkflow(repository, lambda _: True)
    draft = plan()
    assignment = workflow.publish(assignment_id="assign-1", athlete_id=7, draft=draft, prescription=prescription(), effective_from=date(2026, 8, 10), actor_id="coach-1", now=datetime(2026, 8, 10, tzinfo=UTC))
    changed = workflow.set_portion(draft, "rice-slot", "50")

    assert assignment.template_revision == 1
    assert assignment.days[0].meals[0].items[0].amount == Decimal("100")
    assert assignment.days[0].meals[0].items[0].food.facts_revision == "label-8"
    assert assignment.prescription.revision == 4
    assert changed.days != assignment.days
    assert repository.get_draft("template-1").status is DraftStatus.PUBLISHED


def test_entitlement_gates_publish_and_current_but_never_history():
    enabled = True
    workflow = MealPlanWorkflow(InMemoryMealPlanRepository(), lambda _: enabled)
    assignment = workflow.publish(assignment_id="assign-1", athlete_id=7, draft=plan(), prescription=prescription(), effective_from=date(2026, 8, 10), actor_id="coach-1")
    enabled = False

    assert workflow.current_for_athlete(7, date(2026, 8, 10)) is None
    assert workflow.historical_for_athlete(7) == (assignment,)
    with pytest.raises(PermissionError):
        workflow.publish(assignment_id="assign-2", athlete_id=8, draft=plan(), prescription=prescription(), effective_from=date(2026, 8, 10), actor_id="coach-1")


def test_preview_blocks_structure_and_requires_reason_for_macro_exception():
    workflow = MealPlanWorkflow(InMemoryMealPlanRepository(), lambda _: True)
    mismatch = replace(prescription(), targets=MacroTotals(3000, 200, 400, 90, 40))
    with pytest.raises(PublicationError, match="override reason"):
        workflow.publish(assignment_id="a", athlete_id=7, draft=plan(), prescription=mismatch, effective_from=date(2026, 8, 10), actor_id="c")
    assignment = workflow.publish(assignment_id="a", athlete_id=7, draft=plan(), prescription=mismatch, effective_from=date(2026, 8, 10), actor_id="c", override_reason="Intentional phased increase")
    assert assignment.publication_note == "Intentional phased increase"


def test_repository_rejects_stale_draft_and_overlapping_assignment():
    repository = InMemoryMealPlanRepository()
    workflow = MealPlanWorkflow(repository, lambda _: True)
    workflow.save_draft(plan())
    with pytest.raises(WorkflowConflictError, match="stale"):
        workflow.save_draft(replace(plan(), revision=2), expected_revision=9)
