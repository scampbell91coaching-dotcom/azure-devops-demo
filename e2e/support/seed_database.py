"""Deterministic records for browser tests. Never point this at a shared database."""

from __future__ import annotations

from flask import Flask

from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.exercise_library import Exercise
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.models.user import User, UserRole
from werkzeug.security import generate_password_hash


def seed_database(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        alex = db.session.get(Athlete, 101) or Athlete(
            id=101,
            first_name="Alex",
            last_name="Rivera",
            email="alex.e2e@example.test",
            bodyweight_kg=82.5,
            weight_class="83 kg",
            federation="GBPF",
            next_competition="E2E Open",
        )
        sam = db.session.get(Athlete, 202) or Athlete(
            id=202,
            first_name="Sam",
            last_name="Morgan",
            email="sam.private@example.test",
            bodyweight_kg=68.0,
        )
        block = db.session.get(TrainingBlock, 301) or TrainingBlock(
            id=301,
            athlete=alex,
            name="Deterministic strength block",
            objective="Build competition strength",
            status="active",
        )
        week = db.session.get(TrainingWeek, 401) or TrainingWeek(
            id=401, block=block, name="Foundation week", position=1
        )
        session = db.session.get(TrainingSession, 501) or TrainingSession(
            id=501, week=week, name="Squat day", day_label="Monday", position=1
        )
        prescription = db.session.get(
            ExercisePrescription, 601
        ) or ExercisePrescription(
            id=601,
            session=session,
            exercise_name="Competition Squat",
            position=1,
            sets=3,
            reps="5",
            rpe=7.0,
        )
        settings = AthleteCheckinSettings.query.filter_by(
            athlete_id=alex.id
        ).one_or_none() or AthleteCheckinSettings(
            athlete=alex,
            training_enabled=True,
            nutrition_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )
        squat = Exercise.query.filter_by(
            name="Competition Squat"
        ).one_or_none() or Exercise(
            id=701,
            name="Competition Squat",
            movement="squat",
            category="main",
            fatigue_rating=4,
        )
        pulldown = Exercise.query.filter_by(
            name="Lat Pulldown"
        ).one_or_none() or Exercise(
            id=702,
            name="Lat Pulldown",
            movement="accessory",
            category="accessory",
            fatigue_rating=2,
            accessory_suitable=True,
        )
        row = Exercise.query.filter_by(name="Cable Row").one_or_none() or Exercise(
            name="Cable Row",
            movement="accessory",
            category="upper body",
            fatigue_rating=2,
            accessory_suitable=True,
        )
        split_squat = Exercise.query.filter_by(
            name="Bulgarian Split Squat"
        ).one_or_none() or Exercise(
            name="Bulgarian Split Squat",
            movement="accessory",
            category="lower body",
            fatigue_rating=3,
            accessory_suitable=True,
        )
        plank = Exercise.query.filter_by(
            name="Weighted Plank"
        ).one_or_none() or Exercise(
            name="Weighted Plank",
            movement="accessory",
            category="trunk",
            fatigue_rating=2,
            accessory_suitable=True,
        )
        coach = User.query.filter_by(
            email="coach.e2e@example.test"
        ).one_or_none() or User(
            email="coach.e2e@example.test",
            role=UserRole.COACH,
            password_hash=generate_password_hash(
                "Coach E2E password!", method="scrypt"
            ),
        )
        athlete_user = User.query.filter_by(email=alex.email).one_or_none() or User(
            email=alex.email,
            role=UserRole.ATHLETE,
            athlete_id=alex.id,
            password_hash=generate_password_hash(
                "Athlete E2E password!", method="scrypt"
            ),
        )
        db.session.add_all(
            [
                alex,
                sam,
                block,
                week,
                session,
                prescription,
                settings,
                squat,
                pulldown,
                row,
                split_squat,
                plank,
                coach,
                athlete_user,
            ]
        )
        db.session.commit()
