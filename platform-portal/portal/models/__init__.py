"""Coaching database models registered with SQLAlchemy metadata.

Import this package after ``db.init_app`` so application startup, Alembic, and
database CLI commands all operate on the same complete model set.
"""

from .athlete import Athlete
from .athlete_state import (
    AthleteConstraintFlag,
    AthleteStateFact,
    AthleteStateOverride,
    AthleteStateRecommendation,
    AthleteStateSignal,
    CoachTechnicalObservation,
)
from .checkins import AthleteCheckinSettings, WeeklyCheckin
from .coaching_application import CoachingApplication
from .exercise_library import DayTemplate, DayTemplateExercise, Exercise
from .lead_capture import LeadCapture
from .meet_day import Meet, MeetEntry, MeetLift
from .nutrition_checkin import NutritionCheckIn
from .nutrition_import import DailyNutrition, NutritionImportJob, NutritionProviderConnection
from .platform_snapshot import PlatformSnapshot
from .programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from .user import User, UserRole

__all__ = [
    "Athlete",
    "AthleteConstraintFlag",
    "AthleteStateFact",
    "AthleteStateOverride",
    "AthleteStateRecommendation",
    "AthleteStateSignal",
    "AthleteCheckinSettings",
    "CoachingApplication",
    "CoachTechnicalObservation",
    "DayTemplate",
    "DayTemplateExercise",
    "Exercise",
    "ExercisePrescription",
    "ProgrammingLiftSlot",
    "LeadCapture",
    "Meet",
    "MeetEntry",
    "MeetLift",
    "NutritionCheckIn",
    "DailyNutrition",
    "NutritionImportJob",
    "NutritionProviderConnection",
    "PlatformSnapshot",
    "TrainingBlock",
    "TrainingSession",
    "TrainingSessionLog",
    "TrainingSetResult",
    "TrainingWeek",
    "User",
    "UserRole",
    "WeeklyCheckin",
]
