from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class WarmupProtocol(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_protocols"
    __table_args__ = (
        db.UniqueConstraint("stable_key", "version", name="uq_warmup_protocol_version"),
        db.CheckConstraint("version > 0", name="ck_warmup_protocol_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    stable_key = db.Column(db.String(80), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    steps = db.relationship("WarmupProtocolStep", cascade="all, delete-orphan", order_by="WarmupProtocolStep.position")


class WarmupProtocolStep(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_protocol_steps"
    __table_args__ = (
        db.UniqueConstraint("protocol_id", "position", name="uq_warmup_protocol_step_position"),
        db.CheckConstraint("position > 0", name="ck_warmup_protocol_step_position"),
        db.CheckConstraint("phase IN (10, 20, 30, 40)", name="ck_warmup_protocol_step_phase"),
        db.CheckConstraint("kind IN ('reps', 'duration', 'barbell')", name="ck_warmup_protocol_step_kind"),
        db.CheckConstraint("sets > 0", name="ck_warmup_protocol_step_sets"),
    )
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("warmup_protocols.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    phase = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    sets = db.Column(db.Integer, nullable=False, default=1)
    reps = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    percentage = db.Column(db.Float)
    load_kg = db.Column(db.Float)
    rest_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)


class WarmupAssignment(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_assignments"
    __table_args__ = (db.UniqueConstraint("session_id", "protocol_id", name="uq_warmup_assignment_session_protocol"),)
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("warmup_protocols.id", ondelete="RESTRICT"), nullable=False, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    lift_slot_id = db.Column(
        db.Integer,
        db.ForeignKey("programming_lift_slots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    reason = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    protocol = db.relationship("WarmupProtocol")
    lift_slot = db.relationship("ProgrammingLiftSlot")


class WarmupOverride(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_overrides"
    __table_args__ = (
        db.CheckConstraint("action IN ('remove', 'append')", name="ck_warmup_override_action"),
        db.CheckConstraint("phase IS NULL OR phase IN (10, 20, 30, 40)", name="ck_warmup_override_phase"),
        db.CheckConstraint("kind IS NULL OR kind IN ('reps', 'duration', 'barbell')", name="ck_warmup_override_kind"),
    )
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)
    target_key = db.Column(db.String(120))
    phase = db.Column(db.Integer)
    name = db.Column(db.String(160))
    kind = db.Column(db.String(20))
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    percentage = db.Column(db.Float)
    load_kg = db.Column(db.Float)
    rest_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)
    reason = db.Column(db.String(500), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))


class WarmupPlanSnapshot(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_plan_snapshots"
    __table_args__ = (db.UniqueConstraint("athlete_id", "session_id", name="uq_warmup_snapshot_session"),)
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    resolved_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    resolver_version = db.Column(db.String(20), nullable=False, default="1")
    steps = db.relationship("WarmupPlanSnapshotStep", cascade="all, delete-orphan", order_by="WarmupPlanSnapshotStep.position")


class WarmupPlanSnapshotStep(db.Model):  # type: ignore[name-defined]
    __tablename__ = "warmup_plan_snapshot_steps"
    __table_args__ = (db.UniqueConstraint("snapshot_id", "position", name="uq_warmup_snapshot_step_position"),)
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("warmup_plan_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    phase = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    percentage = db.Column(db.Float)
    load_kg = db.Column(db.Float)
    rest_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)
    source_type = db.Column(db.String(30), nullable=False)
    source_key = db.Column(db.String(120), nullable=False)
    source_version = db.Column(db.Integer)
    reason = db.Column(db.String(500))
