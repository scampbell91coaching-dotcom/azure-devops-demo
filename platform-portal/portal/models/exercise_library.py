from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import inspect, text

from ..extensions import db


class Exercise(db.Model):  # type: ignore[name-defined]
    __tablename__ = "exercises"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True, index=True)

    movement = db.Column(db.String(40), nullable=False, index=True)
    family = db.Column(db.String(120), nullable=True, index=True)
    category = db.Column(db.String(60), nullable=False, default="main")
    variation = db.Column(db.String(120), nullable=True)
    equipment = db.Column(db.String(120), nullable=True)
    aliases = db.Column(db.Text, nullable=True)
    occurrence_count = db.Column(db.Integer, nullable=True)

    primary_muscles = db.Column(db.String(255), nullable=True)
    secondary_muscles = db.Column(db.String(255), nullable=True)

    fatigue_rating = db.Column(db.Integer, nullable=False, default=3)
    default_sets = db.Column(db.Integer, nullable=True)
    default_reps = db.Column(db.String(40), nullable=True)
    default_rpe = db.Column(db.Float, nullable=True)
    default_rest_seconds = db.Column(db.Integer, nullable=True)

    coaching_cues = db.Column(db.Text, nullable=True)
    goal = db.Column(db.String(120), nullable=True)
    difficulty = db.Column(db.String(20), nullable=True)
    setup = db.Column(db.Text, nullable=True)
    execution = db.Column(db.Text, nullable=True)
    common_mistakes = db.Column(db.Text, nullable=True)
    regressions = db.Column(db.Text, nullable=True)
    progressions = db.Column(db.Text, nullable=True)
    cautions = db.Column(db.Text, nullable=True)
    competition_relevance = db.Column(db.String(40), nullable=True)
    prescription_styles = db.Column(db.Text, nullable=True)
    rep_ranges = db.Column(db.String(80), nullable=True)
    warmup_suitable = db.Column(db.Boolean, nullable=False, default=False)
    accessory_suitable = db.Column(db.Boolean, nullable=False, default=False)
    catalogue_version = db.Column(db.Integer, nullable=True)
    video_url = db.Column(db.String(500), nullable=True)

    active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


def ensure_exercise_knowledge_columns() -> None:
    """Add B1 knowledge columns to databases created before this release.

    The portal uses ``create_all`` rather than a migration framework.  Adding
    nullable columns preserves pre-existing exercise-library rows while making
    the import available to existing SQLite deployments.
    """

    column_definitions = {
        "family": "VARCHAR(120)",
        "aliases": "TEXT",
        "occurrence_count": "INTEGER",
        "goal": "VARCHAR(120)",
        "difficulty": "VARCHAR(20)",
        "setup": "TEXT",
        "execution": "TEXT",
        "common_mistakes": "TEXT",
        "regressions": "TEXT",
        "progressions": "TEXT",
        "cautions": "TEXT",
        "competition_relevance": "VARCHAR(40)",
        "prescription_styles": "TEXT",
        "rep_ranges": "VARCHAR(80)",
        "warmup_suitable": "BOOLEAN NOT NULL DEFAULT 0",
        "accessory_suitable": "BOOLEAN NOT NULL DEFAULT 0",
        "catalogue_version": "INTEGER",
    }
    existing_columns = {
        column["name"] for column in inspect(db.engine).get_columns("exercises")
    }

    for column_name, definition in column_definitions.items():
        if column_name not in existing_columns:
            db.session.execute(
                text(f"ALTER TABLE exercises ADD COLUMN {column_name} {definition}")
            )

    db.session.commit()


class DayTemplate(db.Model):  # type: ignore[name-defined]
    __tablename__ = "day_templates"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)

    exercises = db.relationship(
        "DayTemplateExercise",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="DayTemplateExercise.position",
    )


class DayTemplateExercise(db.Model):  # type: ignore[name-defined]
    __tablename__ = "day_template_exercises"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("day_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id = db.Column(
        db.Integer,
        db.ForeignKey("exercises.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    position = db.Column(db.Integer, nullable=False, default=1)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(40), nullable=True)
    rpe = db.Column(db.Float, nullable=True)
    percentage = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    template = db.relationship("DayTemplate", back_populates="exercises")
    exercise = db.relationship("Exercise")
