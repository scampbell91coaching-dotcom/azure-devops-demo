from __future__ import annotations

from datetime import UTC, date, datetime

from ..extensions import db


class AthleteCheckinSettings(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athlete_checkin_settings"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    training_enabled = db.Column(db.Boolean, nullable=False, default=True)
    nutrition_enabled = db.Column(db.Boolean, nullable=False, default=False)
    checkin_day = db.Column(db.Integer, nullable=False, default=0)

    athlete = db.relationship(
        "Athlete",
        backref=db.backref(
            "checkin_settings",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )


class WeeklyCheckin(db.Model):  # type: ignore[name-defined]
    __tablename__ = "weekly_checkins"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    week_ending = db.Column(db.Date, nullable=False, default=date.today)
    training_included = db.Column(db.Boolean, nullable=False, default=False)
    nutrition_included = db.Column(db.Boolean, nullable=False, default=False)

    training_adherence = db.Column(db.Integer)
    fatigue = db.Column(db.Integer)
    recovery = db.Column(db.Integer)
    motivation = db.Column(db.Integer)
    pain_present = db.Column(db.Boolean)
    training_notes = db.Column(db.Text)

    average_bodyweight_kg = db.Column(db.Float)
    calories_average = db.Column(db.Integer)
    protein_average_g = db.Column(db.Integer)
    steps_average = db.Column(db.Integer)
    nutrition_adherence = db.Column(db.Integer)
    nutrition_notes = db.Column(db.Text)

    sleep_quality = db.Column(db.Integer)
    stress = db.Column(db.Integer)
    general_notes = db.Column(db.Text)

    status = db.Column(db.String(30), nullable=False, default="submitted")
    coach_notes = db.Column(db.Text)
    coach_reviewed_at = db.Column(db.DateTime)
    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    athlete = db.relationship(
        "Athlete",
        backref=db.backref(
            "weekly_checkins",
            lazy="dynamic",
            cascade="all, delete-orphan",
        ),
    )

    @property
    def risk_flags(self) -> list[str]:
        flags: list[str] = []

        if self.fatigue is not None and self.fatigue >= 8:
            flags.append("High fatigue")
        if self.recovery is not None and self.recovery <= 4:
            flags.append("Low recovery")
        if self.sleep_quality is not None and self.sleep_quality <= 4:
            flags.append("Poor sleep")
        if self.stress is not None and self.stress >= 8:
            flags.append("High stress")
        if self.pain_present:
            flags.append("Pain reported")

        return flags
