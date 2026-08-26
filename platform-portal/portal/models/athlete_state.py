"""Auditable athlete-state records.

Facts and observations are human supplied.  Signals and recommendations are
machine produced and versioned.  None of these tables is a current-state blob:
history is retained and newer facts explicitly supersede older ones.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from ..extensions import db


def _now() -> datetime:
    return datetime.now(UTC)


class AthleteStateFact(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athlete_state_facts"
    __table_args__ = (
        db.CheckConstraint("source_type IN ('athlete', 'coach', 'import', 'legacy')", name="ck_athlete_state_facts_source"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_type = db.Column(db.String(80), nullable=False, index=True)
    value_json = db.Column(db.JSON, nullable=False)
    source_type = db.Column(db.String(20), nullable=False)
    source_ref = db.Column(db.String(160))
    effective_on = db.Column(db.Date)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)
    recorded_by = db.Column(db.String(160))
    supersedes_id = db.Column(db.Integer, db.ForeignKey("athlete_state_facts.id", ondelete="SET NULL"), unique=True)

    athlete = db.relationship("Athlete", backref="state_facts")
    supersedes = db.relationship("AthleteStateFact", remote_side=[id])


class CoachTechnicalObservation(db.Model):  # type: ignore[name-defined]
    __tablename__ = "coach_technical_observations"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    lift = db.Column(db.String(20), nullable=False, index=True)
    observation = db.Column(db.Text, nullable=False)
    observed_on = db.Column(db.Date, nullable=False, default=date.today)
    source_ref = db.Column(db.String(160))
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)
    recorded_by = db.Column(db.String(160), nullable=False)
    superseded_by_id = db.Column(db.Integer, db.ForeignKey("coach_technical_observations.id", ondelete="SET NULL"), unique=True)

    athlete = db.relationship("Athlete", backref="technical_observations")
    superseded_by = db.relationship("CoachTechnicalObservation", remote_side=[id])


class AthleteConstraintFlag(db.Model):  # type: ignore[name-defined]
    """A reported non-diagnostic irritation or training constraint."""
    __tablename__ = "athlete_constraint_flags"
    __table_args__ = (
        db.CheckConstraint("flag_kind IN ('irritation', 'constraint')", name="ck_athlete_constraint_flags_kind"),
        db.CheckConstraint("reported_by IN ('athlete', 'coach')", name="ck_athlete_constraint_flags_reporter"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    flag_kind = db.Column(db.String(20), nullable=False)
    label = db.Column(db.String(160), nullable=False)
    details = db.Column(db.Text)
    reported_by = db.Column(db.String(20), nullable=False)
    source_ref = db.Column(db.String(160))
    starts_on = db.Column(db.Date, nullable=False, default=date.today)
    resolved_on = db.Column(db.Date)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)

    athlete = db.relationship("Athlete", backref="constraint_flags")


class AthleteStateSignal(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athlete_state_signals"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = db.Column(db.String(36), nullable=False, index=True)
    signal_type = db.Column(db.String(80), nullable=False, index=True)
    value_json = db.Column(db.JSON, nullable=False)
    window_start = db.Column(db.Date)
    window_end = db.Column(db.Date)
    calculation_version = db.Column(db.String(40), nullable=False)
    source_refs_json = db.Column(db.JSON, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    calculated_at = db.Column(db.DateTime, nullable=False, default=_now)

    athlete = db.relationship("Athlete", backref="state_signals")


class AthleteStateRecommendation(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athlete_state_recommendations"
    __table_args__ = (
        db.CheckConstraint("status IN ('proposed', 'accepted', 'dismissed', 'superseded')", name="ck_athlete_state_recommendations_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_type = db.Column(db.String(80), nullable=False, index=True)
    recommendation_json = db.Column(db.JSON, nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    signal_ids_json = db.Column(db.JSON, nullable=False)
    generator_version = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="proposed")
    generated_at = db.Column(db.DateTime, nullable=False, default=_now)
    decided_at = db.Column(db.DateTime)
    decided_by = db.Column(db.String(160))

    athlete = db.relationship("Athlete", backref="state_recommendations")


class AthleteStateOverride(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athlete_state_overrides"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type = db.Column(db.String(30), nullable=False)
    target_ref = db.Column(db.String(160), nullable=False)
    override_json = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    recorded_by = db.Column(db.String(160), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)
    expires_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)

    athlete = db.relationship("Athlete", backref="state_overrides")
