"""Deterministic records for browser tests. Never point this at a shared database."""

from __future__ import annotations

from datetime import UTC, date, datetime

from flask import Flask

from portal.extensions import db
from portal.models.account_token import AccountToken
from portal.models.athlete import Athlete
from portal.models.client_service import ClientServiceChange
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.models.exercise_library import Exercise
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.models.meet_day import Meet, MeetEntry
from portal.models.nutrition_import import (
    DailyNutrition,
    NutritionImportJob,
    NutritionProviderConnection,
)
from portal.models.meal_plan import MealPlanAssignment, MealPlanTemplate
from portal.models.nutrition_prescription import NutritionMacroPrescription
from portal.models.organisation import (
    CoachAthleteOwnership,
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
    OwnershipStatus,
)
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.models.warmup import (
    WarmupAssignment,
    WarmupOverride,
    WarmupPlanSnapshot,
    WarmupPlanSnapshotStep,
    WarmupProtocol,
    WarmupProtocolStep,
)
from portal.models.user import User, UserRole
from portal.programming_services.lift_slots import create as create_lift_slot
from werkzeug.security import generate_password_hash


PILOT_ATHLETE_ID = 303
PILOT_BLOCK_ID = 601
PILOT_SESSION_ID = 801
SERVICE_ATHLETE_ID = 202
INVITATION_ATHLETE_ID = 808
PERFORMANCE_ATHLETE_ID = 404
PERFORMANCE_EMPTY_ATHLETE_ID = 405
TENANT_A_ATHLETE_ID = 1101
TENANT_B_ATHLETE_ID = 2101


def _delete_training_state(athlete_id: int) -> None:
    log_ids = [
        row.id for row in TrainingSessionLog.query.filter_by(athlete_id=athlete_id).all()
    ]
    if log_ids:
        TrainingSetResult.query.filter(
            TrainingSetResult.session_log_id.in_(log_ids)
        ).delete(synchronize_session=False)
        TrainingSessionLog.query.filter(TrainingSessionLog.id.in_(log_ids)).delete(
            synchronize_session=False
        )

    snapshot_ids = [
        row.id for row in WarmupPlanSnapshot.query.filter_by(athlete_id=athlete_id).all()
    ]
    if snapshot_ids:
        WarmupPlanSnapshotStep.query.filter(
            WarmupPlanSnapshotStep.snapshot_id.in_(snapshot_ids)
        ).delete(synchronize_session=False)
        WarmupPlanSnapshot.query.filter(WarmupPlanSnapshot.id.in_(snapshot_ids)).delete(
            synchronize_session=False
        )
    WarmupOverride.query.filter_by(athlete_id=athlete_id).delete(
        synchronize_session=False
    )
    protocol_ids = [
        row.protocol_id
        for row in WarmupAssignment.query.filter_by(athlete_id=athlete_id).all()
    ]
    WarmupAssignment.query.filter_by(athlete_id=athlete_id).delete(
        synchronize_session=False
    )
    if protocol_ids:
        WarmupProtocolStep.query.filter(
            WarmupProtocolStep.protocol_id.in_(protocol_ids)
        ).delete(synchronize_session=False)
        WarmupProtocol.query.filter(WarmupProtocol.id.in_(protocol_ids)).delete(
            synchronize_session=False
        )


def reset_fixture(name: str) -> None:
    """Reset one allow-listed mutable E2E workflow, never the whole database."""
    if name == "services":
        ClientServiceChange.query.filter_by(athlete_id=SERVICE_ATHLETE_ID).delete(
            synchronize_session=False
        )
        settings = AthleteCheckinSettings.query.filter_by(
            athlete_id=SERVICE_ATHLETE_ID
        ).one()
        settings.training_enabled = True
        settings.nutrition_enabled = True
        settings.workflow_active = True
        settings.checkin_day = 0
    elif name == "nutrition-import":
        # Restore the complete nutrition-import fixture boundary. Other E2E
        # workflows may change athlete 101's service entitlements, so import
        # tests must not inherit that mutable state.
        ClientServiceChange.query.filter_by(athlete_id=101).delete(
            synchronize_session=False
        )
        db.session.add_all(
            [
                ClientServiceChange(
                    athlete_id=101,
                    service="training",
                    value="yes",
                    effective_at=datetime(2026, 8, 10),
                ),
                ClientServiceChange(
                    athlete_id=101,
                    service="nutrition",
                    value="yes",
                    effective_at=datetime(2026, 8, 10),
                ),
                ClientServiceChange(
                    athlete_id=101,
                    service="meet_day",
                    value="no",
                    effective_at=datetime(2026, 8, 10),
                ),
                ClientServiceChange(
                    athlete_id=101,
                    service="video_review",
                    value="none",
                    effective_at=datetime(2026, 8, 10),
                ),
            ]
        )

        DailyNutrition.query.filter_by(athlete_id=101).delete(synchronize_session=False)
        NutritionImportJob.query.filter_by(athlete_id=101).delete(
            synchronize_session=False
        )
        NutritionProviderConnection.query.filter_by(athlete_id=101).delete(
            synchronize_session=False
        )
    elif name == "invitation":
        AccountToken.query.filter_by(athlete_id=INVITATION_ATHLETE_ID).delete(
            synchronize_session=False
        )
        User.query.filter_by(athlete_id=INVITATION_ATHLETE_ID).delete(
            synchronize_session=False
        )
    elif name == "training":
        _delete_training_state(101)
    elif name == "check-in":
        WeeklyCheckin.query.filter_by(athlete_id=101).delete(
            synchronize_session=False
        )
    elif name == "meal-plan":
        MealPlanAssignment.query.filter_by(athlete_id=101).delete(synchronize_session=False)
        MealPlanTemplate.query.delete(synchronize_session=False)
        NutritionMacroPrescription.query.filter_by(athlete_id=101).delete(synchronize_session=False)
    else:
        raise KeyError(name)
    db.session.commit()


def reset_pilot_fixture() -> None:
    """Restore only the mutable state owned by the dedicated pilot athlete."""
    pilot = db.session.get(Athlete, PILOT_ATHLETE_ID)
    pilot_block = db.session.get(TrainingBlock, PILOT_BLOCK_ID)
    if pilot is None or pilot_block is None:
        raise RuntimeError("pilot fixture must be seeded before it can be reset")

    _delete_training_state(PILOT_ATHLETE_ID)

    WeeklyCheckin.query.filter_by(athlete_id=PILOT_ATHLETE_ID).delete(
        synchronize_session=False
    )
    NutritionCheckIn.query.filter_by(athlete_id=PILOT_ATHLETE_ID).delete(
        synchronize_session=False
    )
    AthleteCheckinSettings.query.filter_by(athlete_id=PILOT_ATHLETE_ID).delete(
        synchronize_session=False
    )

    AccountToken.query.filter_by(athlete_id=PILOT_ATHLETE_ID).delete(
        synchronize_session=False
    )
    User.query.filter_by(athlete_id=PILOT_ATHLETE_ID).delete(
        synchronize_session=False
    )
    pilot_block.status = "draft"
    db.session.commit()


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
        invitation = db.session.get(Athlete, INVITATION_ATHLETE_ID) or Athlete(
            id=INVITATION_ATHLETE_ID,
            first_name="Invite",
            last_name="Retry",
            email="invite.retry@example.test",
            bodyweight_kg=70.0,
        )
        performance_athlete = db.session.get(Athlete, PERFORMANCE_ATHLETE_ID) or Athlete(
            id=PERFORMANCE_ATHLETE_ID,
            first_name="Morgan",
            last_name="Performance",
            email="morgan.performance@example.test",
            bodyweight_kg=82.5,
            weight_class="83 kg",
            federation="GBPF",
            next_competition="Autumn Open",
        )
        performance_empty_athlete = db.session.get(
            Athlete, PERFORMANCE_EMPTY_ATHLETE_ID
        ) or Athlete(
            id=PERFORMANCE_EMPTY_ATHLETE_ID,
            first_name="Casey",
            last_name="No History",
            email="casey.no-history@example.test",
            bodyweight_kg=None,
            weight_class="69 kg",
        )
        tenant_a_athlete = db.session.get(Athlete, TENANT_A_ATHLETE_ID) or Athlete(
            id=TENANT_A_ATHLETE_ID,
            first_name="Avery",
            last_name="Tenant A",
            email="athlete.a.e2e@example.test",
            bodyweight_kg=80.0,
        )
        tenant_b_athlete = db.session.get(Athlete, TENANT_B_ATHLETE_ID) or Athlete(
            id=TENANT_B_ATHLETE_ID,
            first_name="Blake",
            last_name="Tenant B",
            email="athlete.b.e2e@example.test",
            bodyweight_kg=70.0,
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
        mutation_block = db.session.get(TrainingBlock, 901) or TrainingBlock(
            id=901,
            athlete=alex,
            name="Lift slot persistence fixture",
            objective="Mutation-only browser fixture",
            status="draft",
        )
        mutation_week = db.session.get(TrainingWeek, 902) or TrainingWeek(
            id=902,
            block=mutation_block,
            name="Lift slot persistence week",
            position=1,
        )
        mutation_session = db.session.get(TrainingSession, 903) or TrainingSession(
            id=903,
            week=mutation_week,
            name="Lift slot persistence session",
            day_label="Test",
            position=1,
        )
        mutation_prescription = ExercisePrescription.query.filter_by(
            session=mutation_session,
            exercise_name="Competition Squat",
        ).one_or_none() or ExercisePrescription(
            session=mutation_session,
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
        misleading_assistance.auto_select = False
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
        for exercise in (pulldown, row, split_squat, plank):
            exercise.active = True
            exercise.accessory_suitable = True
            exercise.auto_select = False
        extra_accessory_specs = (
            ("Leg Extension", "lower body", 2),
            ("Leg Curl", "lower body", 2),
            ("Back Extension", "posterior chain", 2),
            ("Dumbbell Lateral Raise", "upper body", 1),
            ("Triceps Pushdown", "upper body", 1),
            ("Dumbbell Curl", "upper body", 1),
            ("Standing Calf Raise", "lower body", 1),
        )

        extra_accessories = []
        for name, category, fatigue_rating in extra_accessory_specs:
            exercise = Exercise.query.filter_by(name=name).one_or_none() or Exercise(
                name=name,
                movement="accessory",
                category=category,
                fatigue_rating=fatigue_rating,
                accessory_suitable=True,
            )
            exercise.active = True
            exercise.movement = "accessory"
            exercise.category = category
            exercise.fatigue_rating = fatigue_rating
            exercise.accessory_suitable = True
            exercise.auto_select = False
            exercise.lift_family = None
            extra_accessories.append(exercise)

        db.session.add_all(extra_accessories)

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
        service_user = User.query.filter_by(email=sam.email).one_or_none() or User(
            email=sam.email,
            role=UserRole.ATHLETE,
            athlete_id=sam.id,
            password_hash=generate_password_hash(
                "Service Athlete password!", method="scrypt"
            ),
        )
        tenant_a_coach = User.query.filter_by(
            email="coach.a.e2e@example.test"
        ).one_or_none() or User(
            email="coach.a.e2e@example.test",
            role=UserRole.COACH,
            password_hash=generate_password_hash(
                "Tenant A coach password!", method="scrypt"
            ),
        )
        tenant_b_owner = User.query.filter_by(
            email="owner.b.e2e@example.test"
        ).one_or_none() or User(
            email="owner.b.e2e@example.test",
            role=UserRole.COACH,
            password_hash=generate_password_hash(
                "Tenant B owner password!", method="scrypt"
            ),
        )
        tenant_b_coach = User.query.filter_by(
            email="coach.b.e2e@example.test"
        ).one_or_none() or User(
            email="coach.b.e2e@example.test",
            role=UserRole.COACH,
            password_hash=generate_password_hash(
                "Tenant B coach password!", method="scrypt"
            ),
        )
        tenant_a_athlete_user = User.query.filter_by(
            email=tenant_a_athlete.email
        ).one_or_none() or User(
            email=tenant_a_athlete.email,
            role=UserRole.ATHLETE,
            athlete_id=tenant_a_athlete.id,
            password_hash=generate_password_hash(
                "Tenant A athlete password!", method="scrypt"
            ),
        )
        tenant_b_athlete_user = User.query.filter_by(
            email=tenant_b_athlete.email
        ).one_or_none() or User(
            email=tenant_b_athlete.email,
            role=UserRole.ATHLETE,
            athlete_id=tenant_b_athlete.id,
            password_hash=generate_password_hash(
                "Tenant B athlete password!", method="scrypt"
            ),
        )
        db.session.add_all(
            [
                alex,
                sam,
                pilot,
                invitation,
                performance_athlete,
                performance_empty_athlete,
                tenant_a_athlete,
                tenant_b_athlete,
                block,
                week,
                session,
                prescription,
                mobile_session,
                mobile_prescription,
                mutation_block,
                mutation_week,
                mutation_session,
                mutation_prescription,
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
                service_user,
                tenant_a_coach,
                tenant_b_owner,
                tenant_b_coach,
                tenant_a_athlete_user,
                tenant_b_athlete_user,
            ]
        )
        db.session.flush()

        tenant_a_org = Organisation.query.filter_by(
            slug="traditional-strength-e2e-a"
        ).one_or_none() or Organisation(
            name="Traditional Strength E2E A", slug="traditional-strength-e2e-a"
        )
        tenant_b_org = Organisation.query.filter_by(
            slug="traditional-strength-e2e-b"
        ).one_or_none() or Organisation(
            name="Traditional Strength E2E B", slug="traditional-strength-e2e-b"
        )
        db.session.add_all([tenant_a_org, tenant_b_org])
        db.session.flush()

        def membership(organisation, user, role):
            with db.session.no_autoflush:
                existing = OrganisationMembership.query.filter_by(
                    organisation_id=organisation.id, user_id=user.id
                ).one_or_none()
            record = existing or OrganisationMembership(
                organisation_id=organisation.id, user_id=user.id, role=role
            )
            record.role = role
            record.status = MembershipStatus.ACTIVE
            return record

        tenant_a_owner_membership = membership(
            tenant_a_org, coach, OrganisationRole.OWNER
        )
        tenant_a_coach_membership = membership(
            tenant_a_org, tenant_a_coach, OrganisationRole.COACH
        )
        tenant_b_owner_membership = membership(
            tenant_b_org, tenant_b_owner, OrganisationRole.OWNER
        )
        tenant_b_coach_membership = membership(
            tenant_b_org, tenant_b_coach, OrganisationRole.COACH
        )
        db.session.add_all(
            [
                tenant_a_owner_membership,
                tenant_a_coach_membership,
                tenant_b_owner_membership,
                tenant_b_coach_membership,
            ]
        )
        db.session.flush()

        def ownership(organisation, coach_membership, athlete):
            with db.session.no_autoflush:
                existing = CoachAthleteOwnership.query.filter_by(
                    organisation_id=organisation.id, athlete_id=athlete.id
                ).one_or_none()
            record = existing or CoachAthleteOwnership(
                organisation_id=organisation.id, athlete_id=athlete.id
            )
            record.coach_membership_id = coach_membership.id
            record.status = OwnershipStatus.ACTIVE
            return record

        db.session.add_all(
            [
                # The primary coach login resolves tenant A through its sole
                # active membership. All legacy workflow athletes therefore
                # need canonical ownership by that same membership.
                ownership(tenant_a_org, tenant_a_owner_membership, alex),
                ownership(tenant_a_org, tenant_a_owner_membership, sam),
                ownership(tenant_a_org, tenant_a_owner_membership, pilot),
                ownership(tenant_a_org, tenant_a_owner_membership, invitation),
                ownership(
                    tenant_a_org,
                    tenant_a_owner_membership,
                    performance_athlete,
                ),
                ownership(
                    tenant_a_org,
                    tenant_a_owner_membership,
                    performance_empty_athlete,
                ),
                ownership(tenant_a_org, tenant_a_coach_membership, tenant_a_athlete),
                ownership(tenant_b_org, tenant_b_coach_membership, tenant_b_athlete),
            ]
        )

        # Dedicated, immutable performance-dashboard data. Keeping these rows on
        # their own athletes means mutable training E2E workflows cannot make
        # analytics assertions order-dependent when Playwright uses many workers.
        current_performance_block = db.session.get(TrainingBlock, 1401) or TrainingBlock(
            id=1401,
            athlete=performance_athlete,
            name="Peak strength block",
            objective="Prepare the competition lifts",
            status="active",
        )
        db.session.add(current_performance_block)
        prior_performance_block = db.session.get(TrainingBlock, 1402) or TrainingBlock(
            id=1402,
            athlete=performance_athlete,
            name="Base strength block",
            objective="Establish baseline strength",
            status="archived",
        )
        db.session.add_all([current_performance_block, prior_performance_block])
        db.session.flush()

        current_performance_week = db.session.get(TrainingWeek, 1411) or TrainingWeek(
            id=1411,
            block=current_performance_block,
            name="Peak week",
            position=1,
        )
        db.session.add(current_performance_week)
        prior_performance_week = db.session.get(TrainingWeek, 1412) or TrainingWeek(
            id=1412,
            block=prior_performance_block,
            name="Base week",
            position=1,
        )
        db.session.add_all([current_performance_week, prior_performance_week])
        db.session.flush()

        current_performance_session = db.session.get(
            TrainingSession, 1421
        ) or TrainingSession(
            id=1421,
            week=current_performance_week,
            name="SBD performance day",
            day_label="Saturday",
            position=1,
        )
        db.session.add(current_performance_session)
        prior_performance_session = db.session.get(
            TrainingSession, 1422
        ) or TrainingSession(
            id=1422,
            week=prior_performance_week,
            name="Baseline squat day",
            day_label="Saturday",
            position=1,
        )
        db.session.add_all([current_performance_session, prior_performance_session])
        db.session.flush()

        performance_slots = []
        for row_id, target_session, family, position in (
            (1425, current_performance_session, "squat", 1),
            (1426, current_performance_session, "bench", 2),
            (1427, current_performance_session, "deadlift", 3),
            (1428, prior_performance_session, "squat", 1),
        ):
            slot = db.session.get(ProgrammingLiftSlot, row_id) or ProgrammingLiftSlot(
                id=row_id,
                session=target_session,
                lift_family=family,
                position=position,
            )
            performance_slots.append(slot)
            db.session.add(slot)
        db.session.add_all(performance_slots)
        db.session.flush()

        performance_prescriptions = []
        for row_id, target_session, slot, exercise, position, reps, load, rpe in (
            (1431, current_performance_session, performance_slots[0], squat, 1, "3", 145.0, 8.0),
            (1432, current_performance_session, performance_slots[1], bench, 2, "5", 100.0, 8.0),
            (1433, current_performance_session, performance_slots[2], deadlift, 3, "3", 180.0, 8.0),
            (1434, prior_performance_session, performance_slots[3], squat, 1, "3", 140.0, 8.0),
        ):
            performance_prescription = db.session.get(
                ExercisePrescription, row_id
            ) or ExercisePrescription(
                id=row_id,
                session=target_session,
                lift_slot=slot,
                exercise=exercise,
                exercise_name=exercise.name,
                position=position,
                sets=1,
                reps=reps,
                load_kg=load,
                rpe=rpe,
                slot_role="top_set",
                provenance="coach_authored",
                prescription_type="rpe",
            )
            performance_prescriptions.append(performance_prescription)
            db.session.add(performance_prescription)
        db.session.add_all(performance_prescriptions)
        db.session.flush()

        current_log = db.session.get(TrainingSessionLog, 1441) or TrainingSessionLog(
            id=1441,
            athlete_id=PERFORMANCE_ATHLETE_ID,
            session=current_performance_session,
            session_name=current_performance_session.name,
            block_name=current_performance_block.name,
            week_name=current_performance_week.name,
            status="completed",
            started_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
            completed_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        )
        prior_log = db.session.get(TrainingSessionLog, 1442) or TrainingSessionLog(
            id=1442,
            athlete_id=PERFORMANCE_ATHLETE_ID,
            session=prior_performance_session,
            session_name=prior_performance_session.name,
            block_name=prior_performance_block.name,
            week_name=prior_performance_week.name,
            status="completed",
            started_at=datetime(2026, 7, 11, 9, 0, tzinfo=UTC),
            completed_at=datetime(2026, 7, 11, 10, 0, tzinfo=UTC),
        )
        db.session.add_all([current_log, prior_log])
        db.session.flush()

        for row_id, log, prescription_row, position, load, reps, actual_rpe in (
            (1451, current_log, performance_prescriptions[0], 1, 150.0, 3, 8.0),
            (1452, current_log, performance_prescriptions[1], 2, 100.0, 5, 8.5),
            (1453, current_log, performance_prescriptions[2], 3, 180.0, 2, 9.0),
            (1454, prior_log, performance_prescriptions[3], 1, 140.0, 3, 8.0),
        ):
            result = db.session.get(TrainingSetResult, row_id) or TrainingSetResult(
                id=row_id,
                session_log=log,
                prescription=prescription_row,
                exercise_name=prescription_row.exercise_name,
                exercise_position=position,
                set_order=1,
                prescribed_reps=prescription_row.reps,
                prescribed_load_kg=prescription_row.load_kg,
                prescribed_rpe=prescription_row.rpe,
                completed=True,
                skipped=False,
                actual_load_kg=load,
                actual_reps=reps,
                actual_rpe=actual_rpe,
            )
            db.session.add(result)

        for row_id, observed_on, bodyweight in (
            (1461, date(2026, 7, 12), 83.0),
            (1462, date(2026, 8, 9), 82.5),
        ):
            checkin = db.session.get(WeeklyCheckin, row_id) or WeeklyCheckin(
                id=row_id,
                athlete_id=PERFORMANCE_ATHLETE_ID,
                week_ending=observed_on,
                nutrition_included=True,
                average_bodyweight_kg=bodyweight,
                status="submitted",
            )
            db.session.add(checkin)

        performance_meet = db.session.get(Meet, 1471) or Meet(
            id=1471,
            name="Autumn Open",
            meet_date=date(2026, 9, 20),
            status="planned",
            federation="GBPF",
            weight_class="83 kg",
        )
        db.session.add(performance_meet)
        db.session.flush()
        performance_entry = db.session.get(MeetEntry, 1472) or MeetEntry(
            id=1472,
            meet=performance_meet,
            athlete=performance_athlete,
            flight=1,
            platform_order=1,
        )
        db.session.add(performance_entry)

        service_settings = AthleteCheckinSettings.query.filter_by(
            athlete_id=sam.id
        ).one_or_none() or AthleteCheckinSettings(
            athlete=sam,
            training_enabled=True,
            nutrition_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )
        db.session.add(service_settings)
        db.session.flush()
        service_block = db.session.get(TrainingBlock, 1201) or TrainingBlock(
            id=1201,
            athlete=sam,
            name="Service isolation block",
            objective="Keep entitlement tests independent",
            status="active",
        )
        db.session.add(service_block)
        db.session.flush()
        service_week = db.session.get(TrainingWeek, 1202) or TrainingWeek(
            id=1202, block=service_block, name="Service week", position=1
        )
        db.session.add(service_week)
        db.session.flush()
        service_session = db.session.get(TrainingSession, 1203) or TrainingSession(
            id=1203,
            week=service_week,
            name="Service athlete session",
            day_label="Wednesday",
            position=1,
        )
        db.session.add(service_session)
        db.session.flush()
        service_prescription = ExercisePrescription.query.filter_by(
            session=service_session, exercise_name="Competition Squat"
        ).one_or_none() or ExercisePrescription(
            session=service_session,
            exercise=squat,
            exercise_name="Competition Squat",
            position=1,
            sets=3,
            reps="5",
            rpe=7.0,
        )
        db.session.add_all(
            [
                service_prescription,
            ]
        )

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
            notes=(
                "Warm-up: 5 minutes easy movement; then squat with the empty bar "
                "for 2 x 10, 60 kg x 5, 80 kg x 3, 100 kg x 1. Stop and contact "
                "the coach through the agreed support channel if pain occurs."
            ),
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
            (mutation_session, mutation_prescription, squat, "squat", 1),
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
