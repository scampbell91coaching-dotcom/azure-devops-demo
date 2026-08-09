from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class UserRole(StrEnum):
    COACH = "coach"
    ATHLETE = "athlete"


class User(db.Model):  # type: ignore[name-defined]
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint("role IN ('coach', 'athlete')", name="ck_users_role"),
        db.CheckConstraint(
            "(role = 'coach' AND athlete_id IS NULL) OR "
            "(role = 'athlete' AND athlete_id IS NOT NULL)",
            name="ck_users_role_athlete",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(512), nullable=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    athlete = db.relationship("Athlete", backref=db.backref("user", uselist=False))

    def set_password(self, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Passwords must contain at least 12 characters.")
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return bool(self.password_hash) and check_password_hash(
            self.password_hash, password
        )

    @property
    def user_role(self) -> UserRole:
        return UserRole(self.role)
