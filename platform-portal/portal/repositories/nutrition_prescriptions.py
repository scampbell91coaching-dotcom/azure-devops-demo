from __future__ import annotations

from datetime import UTC

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.nutrition_prescription import NutritionMacroPrescription
from ..services.nutrition_prescriptions import MacroPrescription, MacroTargets, PrescriptionConflictError, PrescriptionProvenance


def _targets(value: dict | None) -> MacroTargets | None:
    return MacroTargets(**value) if value else None


class SqlAlchemyMacroPrescriptionRepository:
    def list_for_athlete(self, athlete_id: int):
        rows = (NutritionMacroPrescription.query.filter_by(athlete_id=athlete_id)
                .order_by(NutritionMacroPrescription.effective_from.desc(), NutritionMacroPrescription.created_at.desc()).all())
        return tuple(self._domain(row) for row in rows)

    def add(self, prescription: MacroPrescription) -> None:
        row = NutritionMacroPrescription(
            id=prescription.prescription_id, athlete_id=prescription.athlete_id,
            effective_from=prescription.effective_from, effective_until=prescription.effective_until,
            calories=prescription.daily_targets.calories, protein_g=prescription.daily_targets.protein_g,
            carbohydrate_g=prescription.daily_targets.carbohydrate_g, fat_g=prescription.daily_targets.fat_g,
            fibre_g=prescription.daily_targets.fibre_g,
            training_targets=self._json(prescription.training_day_targets), rest_targets=self._json(prescription.rest_day_targets),
            meal_count=prescription.meal_count, coach_notes=prescription.notes,
            created_by_user_id=int(prescription.provenance.actor_id), created_at=prescription.provenance.recorded_at,
        )
        db.session.add(row)
        try:
            db.session.flush()
        except IntegrityError as exc:
            db.session.rollback()
            raise PrescriptionConflictError("effective period overlaps an existing prescription") from exc

    @staticmethod
    def _json(targets: MacroTargets | None):
        return None if targets is None else {
            "calories": targets.calories, "protein_g": targets.protein_g,
            "carbohydrate_g": targets.carbohydrate_g, "fat_g": targets.fat_g, "fibre_g": targets.fibre_g,
        }

    @staticmethod
    def _domain(row: NutritionMacroPrescription) -> MacroPrescription:
        return MacroPrescription(
            prescription_id=row.id, athlete_id=row.athlete_id,
            daily_targets=MacroTargets(row.calories, row.protein_g, row.carbohydrate_g, row.fat_g, row.fibre_g),
            effective_from=row.effective_from, effective_until=row.effective_until,
            training_day_targets=_targets(row.training_targets), rest_day_targets=_targets(row.rest_targets),
            meal_count=row.meal_count, notes=row.coach_notes,
            provenance=PrescriptionProvenance(actor_id=str(row.created_by_user_id), actor_role="coach", recorded_at=row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at),
        )
