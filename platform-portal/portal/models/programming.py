from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class TrainingBlock(db.Model):  # type: ignore[name-defined]
    __tablename__ = "training_blocks"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(160), nullable=False)
    objective = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="draft", index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    athlete = db.relationship("Athlete", backref="training_blocks")
    weeks = db.relationship(
        "TrainingWeek",
        back_populates="block",
        cascade="all, delete-orphan",
        order_by="TrainingWeek.position",
    )


class TrainingWeek(db.Model):  # type: ignore[name-defined]
    __tablename__ = "training_weeks"

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(
        db.Integer,
        db.ForeignKey("training_blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    notes = db.Column(db.Text, nullable=True)

    block = db.relationship("TrainingBlock", back_populates="weeks")
    sessions = db.relationship(
        "TrainingSession",
        back_populates="week",
        cascade="all, delete-orphan",
        order_by="TrainingSession.position",
    )


class TrainingSession(db.Model):  # type: ignore[name-defined]
    __tablename__ = "training_sessions"

    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(
        db.Integer,
        db.ForeignKey("training_weeks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    day_label = db.Column(db.String(80), nullable=True)
    position = db.Column(db.Integer, nullable=False, default=1)
    notes = db.Column(db.Text, nullable=True)

    week = db.relationship("TrainingWeek", back_populates="sessions")
    prescriptions = db.relationship(
        "ExercisePrescription",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ExercisePrescription.position",
    )


class ExercisePrescription(db.Model):  # type: ignore[name-defined]
    __tablename__ = "exercise_prescriptions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_name = db.Column(db.String(160), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(40), nullable=True)
    load_kg = db.Column(db.Float, nullable=True)
    percentage = db.Column(db.Float, nullable=True)
    rpe = db.Column(db.Float, nullable=True)
    tempo = db.Column(db.String(40), nullable=True)
    rest_seconds = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    session = db.relationship("TrainingSession", back_populates="prescriptions")
