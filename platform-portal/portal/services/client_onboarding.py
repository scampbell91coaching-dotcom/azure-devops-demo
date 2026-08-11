from __future__ import annotations

from dataclasses import dataclass

from ..models.account_token import AccountToken, AccountTokenPurpose
from ..models.athlete import Athlete
from ..models.athlete_state import AthleteStateFact
from ..models.checkins import AthleteCheckinSettings
from ..models.programming import TrainingBlock
from .account_lifecycle import account_state
from .athlete_state import latest_facts
from .client_services import effective_client_service_profile


STEP_KEYS = ("invite", "account", "goals", "services", "programme", "checkin", "ready")


@dataclass(frozen=True)
class OnboardingStep:
    key: str
    label: str
    complete: bool
    current: bool
    detail: str


@dataclass(frozen=True)
class ClientOnboarding:
    athlete: Athlete
    steps: tuple[OnboardingStep, ...]
    current_step: str
    goals: dict[str, str]
    active_programme: TrainingBlock | None
    draft_programmes: tuple[TrainingBlock, ...]
    checkin_settings: AthleteCheckinSettings | None

    @property
    def ready(self) -> bool:
        return self.current_step == "ready"


def _has_invitation(athlete_id: int) -> bool:
    return AccountToken.query.filter_by(
        athlete_id=athlete_id, purpose=AccountTokenPurpose.INVITATION.value
    ).first() is not None


def build_client_onboarding(athlete: Athlete) -> ClientOnboarding:
    facts = latest_facts(athlete.id)
    goals_fact = facts.get("onboarding_goals")
    goals = goals_fact.value_json if goals_fact and isinstance(goals_fact.value_json, dict) else {}
    services_recorded = "onboarding_services" in facts
    checkin_recorded = "onboarding_checkin_setup" in facts
    profile = effective_client_service_profile(athlete.id)
    active = (
        TrainingBlock.query.filter_by(athlete_id=athlete.id, status="active")
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    drafts = tuple(
        TrainingBlock.query.filter_by(athlete_id=athlete.id, status="draft")
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .all()
    )
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()
    programme_complete = services_recorded and (
        not profile.training_coaching_enabled or active is not None
    )
    completion = {
        "invite": _has_invitation(athlete.id),
        "account": account_state(athlete) == "active",
        "goals": goals_fact is not None,
        "services": services_recorded,
        "programme": programme_complete,
        "checkin": checkin_recorded and settings is not None,
    }
    current = next((key for key in STEP_KEYS[:-1] if not completion[key]), "ready")
    details = {
        "invite": "Invitation issued" if completion["invite"] else "Send secure account invitation",
        "account": "Account activated" if completion["account"] else "Waiting for athlete activation",
        "goals": "Goals captured" if completion["goals"] else "Capture outcomes and context",
        "services": "Entitlements confirmed" if completion["services"] else "Confirm included services",
        "programme": (
            "Not required for this service profile"
            if services_recorded and not profile.training_coaching_enabled
            else (f"{active.name} published" if active else "Publish an athlete programme")
        ),
        "checkin": "Weekly check-in configured" if completion["checkin"] else "Choose modules and schedule",
        "ready": "Client is ready to start" if current == "ready" else "Complete the preceding steps",
    }
    labels = {
        "invite": "Invite", "account": "Account", "goals": "Goals",
        "services": "Service entitlements", "programme": "Programme",
        "checkin": "Check-in setup", "ready": "Ready",
    }
    steps = tuple(
        OnboardingStep(
            key=key,
            label=labels[key],
            complete=(current == "ready" if key == "ready" else completion[key]),
            current=key == current,
            detail=details[key],
        )
        for key in STEP_KEYS
    )
    return ClientOnboarding(
        athlete=athlete,
        steps=steps,
        current_step=current,
        goals={str(key): str(value) for key, value in goals.items()},
        active_programme=active,
        draft_programmes=drafts,
        checkin_settings=settings,
    )


def require_current(onboarding: ClientOnboarding, step: str) -> None:
    if onboarding.current_step != step:
        raise ValueError(f"Complete {onboarding.current_step.replace('_', ' ')} before this step.")
