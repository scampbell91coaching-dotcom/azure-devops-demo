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


def seed_database(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        alex = Athlete(
            id=101,
            first_name="Alex",
            last_name="Rivera",
            email="alex.e2e@example.test",
            bodyweight_kg=82.5,
            weight_class="83 kg",
            federation="GBPF",
            next_competition="E2E Open",
        )
        sam = Athlete(
            id=202,
            first_name="Sam",
            last_name="Morgan",
            email="sam.private@example.test",
            bodyweight_kg=68.0,
        )
        block = TrainingBlock(
            id=301,
            athlete=alex,
            name="Deterministic strength block",
            objective="Build competition strength",
            status="active",
        )
        week = TrainingWeek(id=401, block=block, name="Foundation week", position=1)
        session = TrainingSession(
            id=501, week=week, name="Squat day", day_label="Monday", position=1
        )
        prescription = ExercisePrescription(
            id=601,
            session=session,
            exercise_name="Competition Squat",
            position=1,
            sets=3,
            reps="5",
            rpe=7.0,
        )
        settings = AthleteCheckinSettings(
            athlete=alex,
            training_enabled=True,
            nutrition_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )
        squat = Exercise(
            id=701,
            name="Competition Squat",
            movement="squat",
            category="main",
            fatigue_rating=4,
        )
        pulldown = Exercise(
            id=702,
            name="Lat Pulldown",
            movement="accessory",
            category="accessory",
            fatigue_rating=2,
        )
        db.session.add_all(
            [alex, sam, block, week, session, prescription, settings, squat, pulldown]
        )
        db.session.commit()
