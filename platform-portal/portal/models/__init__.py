"""Coaching database models registered with SQLAlchemy metadata.

Import this package after ``db.init_app`` so application startup, Alembic, and
database CLI commands all operate on the same complete model set.
"""

from .account_token import AccountToken, AccountTokenPurpose, DeliveryState
from .athlete import Athlete
from .athlete_state import (
    AthleteConstraintFlag,
    AthleteStateFact,
    AthleteStateOverride,
    AthleteStateRecommendation,
    AthleteStateSignal,
    CoachTechnicalObservation,
)
from .billing import BillingWebhookEvent, SubscriptionAccount
from .checkins import AthleteCheckinSettings, WeeklyCheckin
from .client_service import ClientServiceChange
from .coaching_application import CoachingApplication
from .exercise_library import DayTemplate, DayTemplateExercise, Exercise
from .external_coaching_review import ExternalCoachingReview
from .lead_capture import LeadCapture
from .meet_day import Meet, MeetEntry, MeetLift
from .meal_plan import MealPlanAssignment, MealPlanTemplate
from .nutrition_checkin import NutritionCheckIn
from .nutrition_import import DailyNutrition, NutritionImportJob, NutritionProviderConnection
from .nutrition_prescription import NutritionMacroPrescription
from .organisation import (
    CoachAthleteOwnership,
    InvitationStatus,
    MembershipStatus,
    Organisation,
    OrganisationInvitation,
    OrganisationMembership,
    OrganisationRole,
    OwnershipStatus,
)
from .platform_snapshot import PlatformSnapshot
from .support_admin import (
    SupportAccessEvent,
    SupportCapabilityGrant,
    SupportDelegation,
    SupportPrincipalRecord,
)
from .programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    ProgrammeRevision,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from .user import User, UserRole
from .warmup import WarmupAssignment, WarmupOverride, WarmupPlanSnapshot, WarmupPlanSnapshotStep, WarmupProtocol, WarmupProtocolStep

__all__ = [
    "Athlete",
    "AccountToken",
    "AccountTokenPurpose",
    "AthleteConstraintFlag",
    "AthleteStateFact",
    "AthleteStateOverride",
    "AthleteStateRecommendation",
    "AthleteStateSignal",
    "AthleteCheckinSettings",
    "BillingWebhookEvent",
    "CoachingApplication",
    "CoachTechnicalObservation",
    "ClientServiceChange",
    "DayTemplate",
    "DayTemplateExercise",
    "DeliveryState",
    "Exercise",
    "ExercisePrescription",
    "ExternalCoachingReview",
    "ProgrammingLiftSlot",
    "ProgrammeRevision",
    "LeadCapture",
    "Meet",
    "MeetEntry",
    "MeetLift",
    "MealPlanAssignment",
    "MealPlanTemplate",
    "InvitationStatus",
    "Organisation",
    "NutritionCheckIn",
    "DailyNutrition",
    "NutritionImportJob",
    "NutritionProviderConnection",
    "NutritionMacroPrescription",
    "CoachAthleteOwnership",
    "MembershipStatus",
    "OrganisationInvitation",
    "OrganisationMembership",
    "OrganisationRole",
    "OwnershipStatus",
    "PlatformSnapshot",
    "SubscriptionAccount",
    "SupportAccessEvent",
    "SupportCapabilityGrant",
    "SupportDelegation",
    "SupportPrincipalRecord",
    "TrainingBlock",
    "TrainingSession",
    "TrainingSessionLog",
    "TrainingSetResult",
    "TrainingWeek",
    "User",
    "UserRole",
    "WeeklyCheckin",
    "WarmupAssignment", "WarmupOverride", "WarmupPlanSnapshot", "WarmupPlanSnapshotStep", "WarmupProtocol", "WarmupProtocolStep",
]
