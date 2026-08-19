from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class NutritionMacroPrescription(db.Model):  # type: ignore[name-defined]
    """Immutable, coach-authored nutrition targets for an effective period."""

    __tablename__ = "nutrition_macro_prescriptions"
    __table_args__ = (
        db.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_nutrition_macro_period"),
        db.CheckConstraint("calories BETWEEN 500 AND 10000", name="ck_nutrition_macro_calories"),
        db.CheckConstraint("protein_g BETWEEN 0 AND 500", name="ck_nutrition_macro_protein"),
        db.CheckConstraint("carbohydrate_g BETWEEN 0 AND 1000", name="ck_nutrition_macro_carbohydrate"),
        db.CheckConstraint("fat_g BETWEEN 0 AND 400", name="ck_nutrition_macro_fat"),
        db.CheckConstraint("fibre_g IS NULL OR fibre_g BETWEEN 0 AND 150", name="ck_nutrition_macro_fibre"),
        db.CheckConstraint("meal_count IS NULL OR meal_count BETWEEN 1 AND 12", name="ck_nutrition_macro_meals"),
    )

    id = db.Column(db.String(36), primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    effective_from = db.Column(db.Date, nullable=False, index=True)
    effective_until = db.Column(db.Date)
    calories = db.Column(db.Integer, nullable=False)
    protein_g = db.Column(db.Integer, nullable=False)
    carbohydrate_g = db.Column(db.Integer, nullable=False)
    fat_g = db.Column(db.Integer, nullable=False)
    fibre_g = db.Column(db.Integer)
    training_targets = db.Column(db.JSON)
    rest_targets = db.Column(db.JSON)
    meal_count = db.Column(db.Integer)
    coach_notes = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    athlete = db.relationship("Athlete")
    created_by = db.relationship("User")
