from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class MealPlanTemplate(db.Model):  # type: ignore[name-defined]
    __tablename__ = "meal_plan_templates"

    id = db.Column(db.String(36), primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class MealPlanAssignment(db.Model):  # type: ignore[name-defined]
    __tablename__ = "meal_plan_assignments"
    __table_args__ = (
        db.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_meal_plan_assignment_period"),
    )

    id = db.Column(db.String(36), primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    template_id = db.Column(db.String(36), nullable=False, index=True)
    template_revision = db.Column(db.Integer, nullable=False)
    effective_from = db.Column(db.Date, nullable=False, index=True)
    effective_until = db.Column(db.Date)
    published_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    published_at = db.Column(db.DateTime, nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)


class PdfMealPlan(db.Model):  # type: ignore[name-defined]
    """Immutable-on-publication PDF bytes delivered within an Organisation."""

    __tablename__ = "pdf_meal_plans"
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'published')", name="ck_pdf_meal_plan_status"),
        db.UniqueConstraint(
            "organisation_id", "athlete_id", "revision",
            name="uq_pdf_meal_plan_org_athlete_revision",
        ),
    )

    id = db.Column(db.String(36), primary_key=True)
    organisation_id = db.Column(
        db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True)
    coach_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text)
    effective_from = db.Column(db.Date, nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    content_sha256 = db.Column(db.String(64), nullable=False)
    content_length = db.Column(db.Integer, nullable=False)
    pdf_bytes = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    published_at = db.Column(db.DateTime)
