from __future__ import annotations

from datetime import UTC, date, datetime

from ..extensions import db


class NutritionCheckIn(db.Model):  # type: ignore[name-defined]
    __tablename__ = "nutrition_checkins"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    checkin_date = db.Column(db.Date, nullable=False, default=date.today, index=True)

    bodyweight_kg = db.Column(db.Float, nullable=True)
    calorie_target = db.Column(db.Integer, nullable=True)
    average_calories = db.Column(db.Integer, nullable=True)
    protein_target_g = db.Column(db.Integer, nullable=True)
    average_protein_g = db.Column(db.Integer, nullable=True)
    carbohydrate_target_g = db.Column(db.Integer, nullable=True)
    average_carbohydrate_g = db.Column(db.Integer, nullable=True)
    fat_target_g = db.Column(db.Integer, nullable=True)
    average_fat_g = db.Column(db.Integer, nullable=True)
    average_fibre_g = db.Column(db.Float, nullable=True)
    average_fluid_l = db.Column(db.Float, nullable=True)
    average_steps = db.Column(db.Integer, nullable=True)
    average_sleep_hours = db.Column(db.Float, nullable=True)

    nutrition_adherence = db.Column(db.Integer, nullable=False)
    hunger = db.Column(db.Integer, nullable=False)
    energy = db.Column(db.Integer, nullable=False)
    sleep_quality = db.Column(db.Integer, nullable=False)
    stress = db.Column(db.Integer, nullable=False)
    digestion = db.Column(db.Integer, nullable=False)
    training_performance = db.Column(db.Integer, nullable=False)

    wins = db.Column(db.Text, nullable=True)
    challenges = db.Column(db.Text, nullable=True)
    upcoming_events = db.Column(db.Text, nullable=True)
    questions = db.Column(db.Text, nullable=True)

    coach_response = db.Column(db.Text, nullable=True)
    reviewed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    athlete = db.relationship(
        "Athlete",
        back_populates="nutrition_checkins",
    )

    @property
    def review_status(self) -> str:
        return "reviewed" if self.reviewed else "needs_review"

    @property
    def alerts(self) -> tuple[str, ...]:
        """Neutral data-quality/recovery prompts; never medical conclusions."""
        alerts: list[str] = []
        if self.bodyweight_kg is None:
            alerts.append("Bodyweight not recorded")
        if self.average_calories is None:
            alerts.append("Average calories not recorded")
        if self.average_protein_g is None:
            alerts.append("Average protein not recorded")
        if self.average_sleep_hours is not None and self.average_sleep_hours < 5:
            alerts.append("Sleep duration is below 5 hours")
        if self.energy <= 3:
            alerts.append("Low energy score")
        if self.digestion <= 3:
            alerts.append("Low digestion score")
        if self.hunger >= 9:
            alerts.append("High hunger score")
        if self.nutrition_adherence <= 3:
            alerts.append("Low adherence score")
        return tuple(alerts)
