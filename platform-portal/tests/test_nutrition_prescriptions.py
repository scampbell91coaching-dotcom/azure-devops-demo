from datetime import UTC, date, datetime

import pytest

from portal.services.nutrition_prescriptions import (
    DayType,
    InMemoryMacroPrescriptionRepository,
    MacroPrescription,
    MacroPrescriptionService,
    MacroTargets,
    PrescriptionConflictError,
    PrescriptionProvenance,
)


def targets(calories: int = 2_500) -> MacroTargets:
    return MacroTargets(calories, 180, 300, 65, 30)


def prescription(**changes: object) -> MacroPrescription:
    values = {
        "prescription_id": "macro-1",
        "athlete_id": 7,
        "daily_targets": targets(),
        "effective_from": date(2026, 8, 10),
        "effective_until": date(2026, 8, 31),
        "provenance": PrescriptionProvenance(
            actor_id="coach-4",
            actor_role="coach",
            source_reference="consultation-82",
            recorded_at=datetime(2026, 8, 9, 10, tzinfo=UTC),
        ),
        "meal_count": 4,
        "notes": "Distribute protein across meals.",
    }
    values.update(changes)
    return MacroPrescription(**values)  # type: ignore[arg-type]


def test_resolves_daily_target_and_preserves_coach_context():
    service = MacroPrescriptionService(
        InMemoryMacroPrescriptionRepository([prescription()])
    )

    result = service.resolve(7, date(2026, 8, 15))

    assert result is not None
    assert result.targets == targets()
    assert result.meal_count == 4
    assert result.notes == "Distribute protein across meals."
    assert result.provenance.actor_id == "coach-4"


def test_training_and_rest_variants_fall_back_to_daily_targets():
    item = prescription(
        training_day_targets=targets(2_800), rest_day_targets=targets(2_300)
    )
    service = MacroPrescriptionService(InMemoryMacroPrescriptionRepository([item]))

    assert service.resolve(7, date(2026, 8, 10), DayType.TRAINING).targets.calories == 2_800
    assert service.resolve(7, date(2026, 8, 10), DayType.REST).targets.calories == 2_300
    assert service.resolve(7, date(2026, 8, 10)).targets.calories == 2_500
    assert prescription(training_day_targets=targets(2_800)).targets_for(DayType.REST) == targets()


def test_effective_dates_are_inclusive_and_gaps_return_no_target():
    service = MacroPrescriptionService(
        InMemoryMacroPrescriptionRepository([prescription()])
    )

    assert service.resolve(7, date(2026, 8, 9)) is None
    assert service.resolve(7, date(2026, 8, 10)) is not None
    assert service.resolve(7, date(2026, 8, 31)) is not None
    assert service.resolve(7, date(2026, 9, 1)) is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("calories", 499, "calories"),
        ("protein_g", 501, "protein_g"),
        ("carbohydrate_g", -1, "carbohydrate_g"),
        ("fat_g", 401, "fat_g"),
        ("fibre_g", 151, "fibre_g"),
    ],
)
def test_rejects_macro_values_outside_supported_input_bounds(field, value, message):
    values = dict(calories=2_500, protein_g=180, carbohydrate_g=300, fat_g=65, fibre_g=30)
    values[field] = value
    with pytest.raises(ValueError, match=message):
        MacroTargets(**values)


def test_validates_dates_meals_notes_and_aware_provenance():
    with pytest.raises(ValueError, match="precede"):
        prescription(effective_until=date(2026, 8, 9))
    with pytest.raises(ValueError, match="meal_count"):
        prescription(meal_count=0)
    with pytest.raises(ValueError, match="notes"):
        prescription(notes="x" * 2_001)
    with pytest.raises(ValueError, match="timezone-aware"):
        PrescriptionProvenance("coach-4", "coach", recorded_at=datetime(2026, 8, 9))


def test_assignment_rejects_overlapping_or_duplicate_prescriptions():
    repository = InMemoryMacroPrescriptionRepository([prescription()])
    service = MacroPrescriptionService(repository)

    with pytest.raises(PrescriptionConflictError, match="overlaps"):
        service.assign(
            prescription(
                prescription_id="macro-2",
                effective_from=date(2026, 8, 31),
                effective_until=None,
            )
        )
    with pytest.raises(PrescriptionConflictError, match="already exists"):
        service.assign(
            prescription(
                effective_from=date(2026, 9, 1), effective_until=None
            )
        )


def test_assignment_accepts_adjacent_non_overlapping_periods_and_isolates_athletes():
    repository = InMemoryMacroPrescriptionRepository([prescription()])
    service = MacroPrescriptionService(repository)
    service.assign(
        prescription(
            prescription_id="macro-2",
            effective_from=date(2026, 9, 1),
            effective_until=None,
        )
    )
    service.assign(
        prescription(
            prescription_id="other-athlete",
            athlete_id=8,
            effective_from=date(2026, 8, 10),
            effective_until=None,
        )
    )

    assert service.resolve(7, date(2026, 9, 1)).prescription_id == "macro-2"
    assert service.resolve(8, date(2026, 8, 15)).prescription_id == "other-athlete"


def test_ambiguous_repository_data_fails_loudly():
    repository = InMemoryMacroPrescriptionRepository(
        [prescription(), prescription(prescription_id="macro-2")]
    )
    with pytest.raises(PrescriptionConflictError, match="ambiguous"):
        MacroPrescriptionService(repository).resolve(7, date(2026, 8, 20))


def test_domain_contains_targets_not_actual_intake_or_adherence():
    fields = MacroPrescription.__dataclass_fields__
    assert "actual_calories" not in fields
    assert "adherence" not in fields
    assert "average_calories" not in fields
