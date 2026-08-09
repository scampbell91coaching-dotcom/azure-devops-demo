"""Deterministic records for browser tests. Never point this at a shared database."""

from __future__ import annotations

from flask import Flask

from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.exercise_library import Exercise
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.programming_services.lift_slots import create as create_lift_slot
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
        pilot = db.session.get(Athlete, 303) or Athlete(
            id=303,
            first_name="Taylor",
            last_name="Jordan",
            email="taylor.pilot@example.test",
            bodyweight_kg=74.2,
            weight_class="76 kg",
            federation="GBPF",
            next_competition="First Paying Athlete Open",
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
        prescription = ExercisePrescription.query.filter_by(
            session=session, exercise_name="Competition Squat"
        ).one_or_none() or ExercisePrescription(
            session=session,
            exercise_name="Competition Squat",
            position=1,
            sets=3,
            reps="5",
            rpe=7.0,
        )

        mobile_session = db.session.get(TrainingSession, 502) or TrainingSession(
            id=502,
            week=week,
            name="Mobile test session",
            day_label="Tuesday",
            position=2,
        )
        mobile_prescription = ExercisePrescription.query.filter_by(
            session=mobile_session, exercise_name="Competition Squat"
        ).one_or_none() or ExercisePrescription(
            session=mobile_session,
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
            name="Competition Squat",
            movement="squat",
            category="main",
            fatigue_rating=4,
            lift_family="squat",
        )
        bench = Exercise.query.filter_by(
            name="Competition Bench Press"
        ).one_or_none() or Exercise(
            name="Competition Bench Press",
            movement="bench",
            category="main",
            fatigue_rating=3,
            lift_family="bench",
        )
        deadlift = Exercise.query.filter_by(
            name="Competition Deadlift"
        ).one_or_none() or Exercise(
            name="Competition Deadlift",
            movement="deadlift",
            category="main",
            fatigue_rating=5,
            lift_family="deadlift",
        )
        misleading_assistance = Exercise.query.filter_by(
            name="Squat Named Row"
        ).one_or_none() or Exercise(
            name="Squat Named Row",
            movement="accessory",
            category="upper body",
            fatigue_rating=2,
            accessory_suitable=True,
        )

        conventional_deadlift = Exercise.query.filter_by(
            name="Conventional Deadlift"
        ).one_or_none() or Exercise(
            name="Conventional Deadlift",
            movement="deadlift",
            category="main",
            fatigue_rating=5,
            lift_family="deadlift",
        )
        sumo_deadlift = Exercise.query.filter_by(
            name="Sumo Deadlift"
        ).one_or_none() or Exercise(
            name="Sumo Deadlift",
            movement="deadlift",
            category="main",
            fatigue_rating=5,
            lift_family="deadlift",
        )

        conventional_deadlift.active = True
        conventional_deadlift.lift_family = "deadlift"
        sumo_deadlift.active = True
        sumo_deadlift.lift_family = "deadlift"
        # Keep canonical E2E exercise taxonomy deterministic even when
        # seed rows already exist from an earlier run.
        squat.movement = "squat"
        squat.category = "main"
        squat.fatigue_rating = 4
        squat.lift_family = "squat"

        bench.movement = "bench"
        bench.category = "main"
        bench.fatigue_rating = 3
        bench.lift_family = "bench"

        deadlift.movement = "deadlift"
        deadlift.category = "main"
        deadlift.fatigue_rating = 5
        deadlift.lift_family = "deadlift"

        misleading_assistance.movement = "accessory"
        misleading_assistance.category = "upper body"
        misleading_assistance.fatigue_rating = 2
        misleading_assistance.accessory_suitable = True
        misleading_assistance.lift_family = None

        extra_prescriptions = []
        for name, position in (
            ("Competition Bench Press", 2),
            ("Competition Deadlift", 3),
            ("Squat Named Row", 4),
        ):
            existing = ExercisePrescription.query.filter_by(
                session=session, exercise_name=name
            ).one_or_none()
            extra_prescriptions.append(
                existing
                or ExercisePrescription(
                    session=session,
                    exercise_name=name,
                    position=position,
                    sets=3,
                    reps="5",
                    rpe=7.0,
                )
            )
        pulldown = Exercise.query.filter_by(
            name="Lat Pulldown"
        ).one_or_none() or Exercise(
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
        pause_squat = Exercise.query.filter_by(
            name="Pause Squat"
        ).one_or_none() or Exercise(
            name="Pause Squat",
            movement="squat",
            category="main",
            fatigue_rating=4,
            lift_family="squat",
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
        pilot_user = User.query.filter_by(email=pilot.email).one_or_none() or User(
            email=pilot.email,
            role=UserRole.ATHLETE,
            athlete_id=pilot.id,
            password_hash=generate_password_hash(
                "Pilot Athlete password!", method="scrypt"
            ),
        )
        db.session.add_all(
            [
                alex,
                sam,
                pilot,
                block,
                week,
                session,
                prescription,
                mobile_session,
                mobile_prescription,
                settings,
                squat,
                bench,
                deadlift,
                conventional_deadlift,
                sumo_deadlift,
                misleading_assistance,
                *extra_prescriptions,
                pulldown,
                row,
                pause_squat,
                split_squat,
                plank,
                coach,
                athlete_user,
                pilot_user,
            ]
        )
        db.session.flush()

        # This is deliberately a draft fixture: the browser test must publish it
        # through the supported coach UI before the athlete can see or log it.
        pilot_block = db.session.get(TrainingBlock, 601) or TrainingBlock(
            id=601,
            athlete=pilot,
            name="First paying athlete strength pilot",
            objective="Build competition strength with fatigue-controlled volume",
            status="draft",
        )
        db.session.add(pilot_block)
        db.session.flush()
        pilot_week = db.session.get(TrainingWeek, 701) or TrainingWeek(
            id=701,
            block=pilot_block,
            name="Pilot week 1",
            position=1,
            notes="Technical strength exposure",
        )
        db.session.add(pilot_week)
        db.session.flush()
        pilot_session = db.session.get(TrainingSession, 801) or TrainingSession(
            id=801,
            week=pilot_week,
            name="Squat strength and assistance",
            day_label="Monday",
            position=1,
        )
        db.session.add(pilot_session)
        db.session.flush()

        if not pilot_session.lift_slots:
            create_lift_slot(
                pilot_session,
                lift_family="squat",
                top_exercise=squat,
                top_sets=1,
                top_reps="3",
                top_load_kg=120,
                top_rpe_min=7.5,
                top_rpe_max=8.5,
                back_off_exercise=pause_squat,
                back_off_sets=2,
                back_off_reps="5",
                back_off_load_kg=100,
                back_off_rpe_min=6.5,
                back_off_rpe_max=7.5,
            )
            db.session.add(
                ExercisePrescription(
                    session=pilot_session,
                    exercise=row,
                    exercise_name=row.name,
                    position=3,
                    sets=2,
                    reps="10",
                    rpe_min=6.0,
                    rpe_max=7.0,
                    prescription_type="rpe",
                    provenance="coach_selected",
                )
            )

        lift_rows = (
            (session, prescription, squat, "squat", 1),
            (session, extra_prescriptions[0], bench, "bench", 2),
            (session, extra_prescriptions[1], deadlift, "deadlift", 3),
            (mobile_session, mobile_prescription, squat, "squat", 1),
        )
        for target_session, target_row, target_exercise, family, position in lift_rows:
            slot = ProgrammingLiftSlot.query.filter_by(
                session_id=target_session.id, position=position
            ).one_or_none()
            if slot is None:
                slot = ProgrammingLiftSlot(
                    session=target_session, position=position, lift_family=family
                )
                db.session.add(slot)
            target_row.exercise = target_exercise
            target_row.lift_slot = slot
            target_row.slot_role = "top_set"
            target_row.provenance = "generated"
            target_row.prescription_type = "rpe"
        extra_prescriptions[2].provenance = "generated"
        db.session.commit()
