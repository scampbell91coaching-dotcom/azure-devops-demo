from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import event, inspect, text

from ..extensions import db

PRESCRIPTION_TYPES = {
    "rpe",
    "fixed_load",
    "load_capped",
    "amrap",
    "rep_range",
    "single_target",
}

LIFT_FAMILIES = {"squat", "bench", "deadlift"}
SLOT_ROLES = {"top_set", "back_off"}
PRESCRIPTION_PROVENANCE = {"generated", "coach_selected", "coach_authored"}


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
    revisions = db.relationship(
        "ProgrammeRevision",
        back_populates="block",
        cascade="save-update, merge",
        order_by="ProgrammeRevision.revision_number.desc()",
        passive_deletes=True,
    )


class ProgrammeRevision(db.Model):  # type: ignore[name-defined]
    """An immutable, authored-fidelity snapshot of one programme change."""

    __tablename__ = "programme_revisions"
    __table_args__ = (
        db.UniqueConstraint(
            "block_id", "revision_number", name="uq_programme_revisions_number"
        ),
        db.CheckConstraint(
            "revision_number > 0", name="ck_programme_revisions_number"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(
        db.Integer,
        db.ForeignKey("training_blocks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    athlete_id = db.Column(
        db.Integer, db.ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True,
        index=True,
    )
    revision_number = db.Column(db.Integer, nullable=False)
    change_type = db.Column(db.String(80), nullable=False)
    summary = db.Column(db.String(240), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    authored_snapshot = db.Column(db.JSON, nullable=False)
    authored_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    authored_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authored_by = db.Column(db.String(255), nullable=False)

    block = db.relationship("TrainingBlock", back_populates="revisions")
    author = db.relationship("User")
    athlete = db.relationship("Athlete")


@event.listens_for(ProgrammeRevision, "before_update")
@event.listens_for(ProgrammeRevision, "before_delete")
def _prevent_revision_mutation(*_args: object) -> None:
    raise ValueError("programme revisions are append-only")


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

    def lift_slot_frequencies(self) -> dict[str, int]:
        """Count scheduled exposures, never their top/back-off rows."""
        counts = {family: 0 for family in sorted(LIFT_FAMILIES)}
        for session in self.sessions:
            for slot in session.lift_slots:
                counts[slot.lift_family] += 1
        return counts


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
    lift_slots = db.relationship(
        "ProgrammingLiftSlot",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ProgrammingLiftSlot.position",
    )


class ProgrammingLiftSlot(db.Model):  # type: ignore[name-defined]
    """One scheduled squat, bench, or deadlift exposure."""

    __tablename__ = "programming_lift_slots"
    __table_args__ = (
        db.CheckConstraint("position > 0", name="ck_programming_lift_slots_position"),
        db.CheckConstraint(
            "lift_family IN ('squat', 'bench', 'deadlift')",
            name="ck_programming_lift_slots_family",
        ),
        db.UniqueConstraint(
            "session_id", "position", name="uq_programming_lift_slots_position"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    lift_family = db.Column(db.String(20), nullable=False, index=True)

    session = db.relationship("TrainingSession", back_populates="lift_slots")
    prescriptions = db.relationship(
        "ExercisePrescription",
        back_populates="lift_slot",
        order_by="ExercisePrescription.position",
    )

    def validate(self) -> None:
        if self.lift_family not in LIFT_FAMILIES:
            raise ValueError(f"Unknown lift family: {self.lift_family}")
        if self.position is None or self.position <= 0:
            raise ValueError("lift slot position must be greater than zero")


class TrainingSessionLog(db.Model):  # type: ignore[name-defined]
    """An athlete's immutable-after-completion record of an assigned session."""

    __tablename__ = "training_session_logs"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('in_progress', 'completed')",
            name="ck_training_session_logs_status",
        ),
        db.UniqueConstraint(
            "athlete_id", "session_id", name="uq_training_session_logs_assignment"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_name = db.Column(db.String(120), nullable=False)
    block_name = db.Column(db.String(160), nullable=False)
    week_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="in_progress", index=True)
    started_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    completed_at = db.Column(db.DateTime, nullable=True, index=True)

    athlete = db.relationship("Athlete", backref="training_session_logs")
    session = db.relationship("TrainingSession")
    results = db.relationship(
        "TrainingSetResult",
        back_populates="session_log",
        cascade="all, delete-orphan",
        order_by="(TrainingSetResult.exercise_position, TrainingSetResult.set_order)",
    )


class TrainingSetResult(db.Model):  # type: ignore[name-defined]
    """One stable working-set result with a snapshot of its prescription."""

    __tablename__ = "training_set_results"
    __table_args__ = (
        db.CheckConstraint("set_order > 0", name="ck_training_set_results_order"),
        db.CheckConstraint("actual_load_kg >= 0", name="ck_training_set_results_load"),
        db.CheckConstraint("actual_reps >= 0", name="ck_training_set_results_reps"),
        db.CheckConstraint(
            "actual_rpe >= 1 AND actual_rpe <= 10",
            name="ck_training_set_results_rpe",
        ),
        db.CheckConstraint(
            "NOT (completed AND skipped)",
            name="ck_training_set_results_single_state",
        ),
        db.UniqueConstraint(
            "session_log_id",
            "exercise_position",
            "set_order",
            name="uq_training_set_results_order",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_log_id = db.Column(
        db.Integer,
        db.ForeignKey("training_session_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("exercise_prescriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    exercise_name = db.Column(db.String(160), nullable=False)
    exercise_position = db.Column(db.Integer, nullable=False)
    set_order = db.Column(db.Integer, nullable=False)
    is_extra = db.Column(db.Boolean, nullable=False, default=False)
    prescribed_reps = db.Column(db.String(40), nullable=True)
    prescribed_load_kg = db.Column(db.Float, nullable=True)
    prescribed_rpe = db.Column(db.Float, nullable=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    skipped = db.Column(db.Boolean, nullable=False, default=False)
    actual_load_kg = db.Column(db.Float, nullable=True)
    actual_reps = db.Column(db.Integer, nullable=True)
    actual_rpe = db.Column(db.Float, nullable=True)
    athlete_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    session_log = db.relationship("TrainingSessionLog", back_populates="results")
    prescription = db.relationship("ExercisePrescription")


class ExercisePrescription(db.Model):  # type: ignore[name-defined]
    __tablename__ = "exercise_prescriptions"
    __table_args__ = (
        db.CheckConstraint(
            "slot_role IS NULL OR slot_role IN ('top_set', 'back_off')",
            name="ck_exercise_prescriptions_slot_role",
        ),
        db.CheckConstraint(
            "provenance IS NULL OR provenance IN "
            "('generated', 'coach_selected', 'coach_authored')",
            name="ck_exercise_prescriptions_provenance",
        ),
        db.CheckConstraint(
            "rpe_min IS NULL OR (rpe_min >= 1 AND rpe_min <= 10)",
            name="ck_exercise_prescriptions_rpe_min",
        ),
        db.CheckConstraint(
            "rpe_max IS NULL OR (rpe_max >= 1 AND rpe_max <= 10)",
            name="ck_exercise_prescriptions_rpe_max",
        ),
        db.CheckConstraint(
            "(rpe_min IS NULL AND rpe_max IS NULL) OR "
            "(rpe_min IS NOT NULL AND rpe_max IS NOT NULL AND rpe_min <= rpe_max)",
            name="ck_exercise_prescriptions_rpe_range",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id = db.Column(
        db.Integer,
        db.ForeignKey("exercises.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lift_slot_id = db.Column(
        db.Integer,
        db.ForeignKey("programming_lift_slots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    slot_role = db.Column(db.String(20), nullable=True)
    provenance = db.Column(db.String(30), nullable=True)
    exercise_name = db.Column(db.String(160), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    prescription_type = db.Column(db.String(40), nullable=True)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(40), nullable=True)
    reps_min = db.Column(db.Integer, nullable=True)
    reps_max = db.Column(db.Integer, nullable=True)
    load_kg = db.Column(db.Float, nullable=True)
    load_cap_kg = db.Column(db.Float, nullable=True)
    percentage = db.Column(db.Float, nullable=True)
    rpe = db.Column(db.Float, nullable=True)
    rpe_min = db.Column(db.Float, nullable=True)
    rpe_max = db.Column(db.Float, nullable=True)
    rpe_cap = db.Column(db.Float, nullable=True)
    target_reps = db.Column(db.Integer, nullable=True)
    target_rpe = db.Column(db.Float, nullable=True)
    target_load_kg = db.Column(db.Float, nullable=True)
    amrap = db.Column(db.Boolean, nullable=True)
    tempo = db.Column(db.String(40), nullable=True)
    rest_seconds = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    session = db.relationship("TrainingSession", back_populates="prescriptions")
    exercise = db.relationship("Exercise")
    lift_slot = db.relationship("ProgrammingLiftSlot", back_populates="prescriptions")

    def validate(self) -> None:
        """Validate a typed prescription without changing legacy rows."""
        for name in ("rpe", "rpe_min", "rpe_max", "rpe_cap", "target_rpe"):
            value = getattr(self, name)
            if value is not None and not 1 <= value <= 10:
                raise ValueError(f"{name} must be between 1 and 10")
        for name in ("load_kg", "load_cap_kg", "target_load_kg"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if (
            self.reps_min is not None
            and self.reps_max is not None
            and self.reps_min > self.reps_max
        ):
            raise ValueError("reps_min cannot exceed reps_max")
        if (
            self.rpe_min is not None
            and self.rpe_max is not None
            and self.rpe_min > self.rpe_max
        ):
            raise ValueError("rpe_min cannot exceed rpe_max")
        if (self.rpe_min is None) != (self.rpe_max is None):
            raise ValueError("rpe_min and rpe_max must be provided together")
        if self.rpe is not None and self.rpe_min is not None:
            raise ValueError("use either rpe or an RPE range, not both")
        if self.slot_role is not None and self.slot_role not in SLOT_ROLES:
            raise ValueError(f"Unknown slot role: {self.slot_role}")
        if (
            self.provenance is not None
            and self.provenance not in PRESCRIPTION_PROVENANCE
        ):
            raise ValueError(f"Unknown prescription provenance: {self.provenance}")
        has_slot = self.lift_slot is not None or self.lift_slot_id is not None
        if not has_slot and self.slot_role is not None:
            raise ValueError("slot_role requires a lift slot")
        if has_slot and self.slot_role is None:
            raise ValueError("a lift-slot prescription requires slot_role")
        if self.prescription_type is None:
            return
        if self.prescription_type not in PRESCRIPTION_TYPES:
            raise ValueError(f"Unknown prescription type: {self.prescription_type}")

        for name in ("sets", "reps_min", "reps_max", "target_reps"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be greater than zero")

        required = {
            "rpe": ("sets", "reps"),
            "fixed_load": ("sets", "reps", "load_kg"),
            "load_capped": ("sets", "reps", "load_cap_kg"),
            "rep_range": ("sets", "reps_min", "reps_max"),
        }.get(self.prescription_type, ())
        missing = [name for name in required if getattr(self, name) in (None, "")]
        if missing:
            raise ValueError(f"{self.prescription_type} requires {', '.join(missing)}")
        if (
            self.prescription_type == "rpe"
            and self.rpe is None
            and self.rpe_min is None
        ):
            raise ValueError("rpe requires rpe or an RPE range")
        if self.prescription_type == "amrap":
            if self.sets is None:
                raise ValueError("amrap requires sets")
            if not self.amrap:
                raise ValueError("amrap prescription requires amrap=True")
        if self.prescription_type == "single_target" and all(
            value is None
            for value in (self.target_reps, self.target_rpe, self.target_load_kg)
        ):
            raise ValueError("single_target requires at least one target")

    @property
    def summary(self) -> str:
        """Return a concise, human-readable prescription."""
        if self.prescription_type is None:
            parts = [self._sets_and_reps(self.reps)]
            if self.load_kg is not None:
                parts.append(f"{self._number(self.load_kg)} kg")
            if self.rpe is not None:
                parts.append(f"@ RPE {self._number(self.rpe)}")
            return " ".join(part for part in parts if part)

        reps = self.reps
        if self.prescription_type == "rep_range":
            reps = f"{self.reps_min}-{self.reps_max}"
        parts = [self._sets_and_reps(reps)]
        if self.prescription_type == "fixed_load":
            parts.append(f"@ {self._number(self.load_kg)} kg")
        elif self.prescription_type == "load_capped":
            parts.append(f"up to {self._number(self.load_cap_kg)} kg")
        elif self.prescription_type == "rpe":
            if self.rpe_min is not None:
                parts.append(
                    f"@ RPE {self._number(self.rpe_min)}-{self._number(self.rpe_max)}"
                )
            else:
                parts.append(f"@ RPE {self._number(self.rpe)}")
        elif self.prescription_type == "amrap":
            parts.append("AMRAP")
            if self.rpe_cap is not None:
                parts.append(f"(cap RPE {self._number(self.rpe_cap)})")
        elif self.prescription_type == "single_target":
            targets = []
            if self.target_reps is not None:
                unit = "rep" if self.target_reps == 1 else "reps"
                targets.append(f"{self.target_reps} {unit}")
            if self.target_load_kg is not None:
                targets.append(f"{self._number(self.target_load_kg)} kg")
            if self.target_rpe is not None:
                targets.append(f"RPE {self._number(self.target_rpe)}")
            parts = ["Single target: " + " @ ".join(targets)]
        return " ".join(part for part in parts if part)

    def _sets_and_reps(self, reps: str | None) -> str:
        if self.sets is not None and reps:
            return f"{self.sets} x {reps}"
        if self.sets is not None:
            return f"{self.sets} sets"
        return reps or ""

    @staticmethod
    def _number(value: float | None) -> str:
        return f"{value:g}" if value is not None else ""

    def copy_values(self) -> dict[str, object]:
        """Return all prescription data fields for duplication workflows."""
        names = (
            "exercise_name",
            "exercise_id",
            "position",
            "prescription_type",
            "sets",
            "reps",
            "reps_min",
            "reps_max",
            "load_kg",
            "load_cap_kg",
            "percentage",
            "rpe",
            "rpe_min",
            "rpe_max",
            "rpe_cap",
            "target_reps",
            "target_rpe",
            "target_load_kg",
            "amrap",
            "tempo",
            "rest_seconds",
            "notes",
            "provenance",
        )
        return {name: getattr(self, name) for name in names}


@event.listens_for(ExercisePrescription, "before_insert")
@event.listens_for(ExercisePrescription, "before_update")
def _validate_prescription(_mapper: object, _connection: object, item: object) -> None:
    assert isinstance(item, ExercisePrescription)
    item.validate()


@event.listens_for(ProgrammingLiftSlot, "before_insert")
@event.listens_for(ProgrammingLiftSlot, "before_update")
def _validate_lift_slot(_mapper: object, _connection: object, item: object) -> None:
    assert isinstance(item, ProgrammingLiftSlot)
    item.validate()


def ensure_prescription_mode_columns() -> None:
    """Add nullable prescription-mode columns to existing databases."""
    definitions = {
        "prescription_type": "VARCHAR(40)",
        "reps_min": "INTEGER",
        "reps_max": "INTEGER",
        "rpe_cap": "FLOAT",
        "load_cap_kg": "FLOAT",
        "target_reps": "INTEGER",
        "target_rpe": "FLOAT",
        "target_load_kg": "FLOAT",
        "amrap": "BOOLEAN",
    }
    columns = {
        column["name"]
        for column in inspect(db.engine).get_columns("exercise_prescriptions")
    }
    for name, definition in definitions.items():
        if name not in columns:
            db.session.execute(
                text(
                    f"ALTER TABLE exercise_prescriptions ADD COLUMN {name} {definition}"
                )
            )
    db.session.commit()
