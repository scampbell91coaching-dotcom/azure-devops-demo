from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models.athlete import Athlete
from .models.checkins import AthleteCheckinSettings
from .models.nutrition_checkin import NutritionCheckIn
from .models.programming import TrainingBlock, TrainingSession, TrainingSessionLog
from .models.external_coaching_review import ExternalCoachingReview
from .models.athlete_state import CoachTechnicalObservation
from .services.athlete_dashboard import get_athlete_dashboard
from .services.performance_decisions import build_performance_decisions
from .services.coach_athlete_performance import get_coach_athlete_performance
from .services.athlete_services import athlete_services
from .services.training_schedule import project_training_schedule
from .services.nutrition_dashboard import get_nutrition_dashboard
from .services.nutrition_entitlements import nutrition_coaching_enabled
from .nutrition_imports import _summary
from .services.training_log import assigned_log, save_training_session
from .services.persisted_warmups import athlete_warmup
from .auth import roles_required
from .models.account_token import AccountTokenPurpose, DeliveryState
from .models.user import UserRole
from .models.client_service import ClientServiceChange
from .services.client_services import (
    SERVICE_DEFINITIONS,
    effective_client_service_profile,
    resolved_client_services,
)
from .services.account_lifecycle import (
    AccountLifecycleError,
    account_state,
    create_invitation,
    create_password_reset,
    latest_token,
    revoke_tokens,
)
from .models.athlete_state import AthleteStateFact
from .services.athlete_state import record_fact
from .services.client_onboarding import build_client_onboarding, require_current
from .programming_services.blocks import BlockActivationError, activate

athletes_bp = Blueprint("athletes", __name__)


@athletes_bp.get("/nutrition")
def nutrition_dashboard():
    return render_template(
        "nutrition/index.html",
        dashboard=get_nutrition_dashboard(),
    )


@athletes_bp.get("/athlete/dashboard")
def dashboard():
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)

    dashboard_data = get_athlete_dashboard(
        athlete_id,
        today=datetime.now(UTC).date(),
    )
    if dashboard_data is None:
        abort(401)

    return render_template(
        "athletes/athlete_dashboard.html",
        dashboard=dashboard_data,
        today=datetime.now(UTC).date(),
    )


def _signed_in_athlete_id() -> int:
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)
    return athlete_id


@athletes_bp.get("/athlete/programme")
def programme():
    athlete_id = _signed_in_athlete_id()
    if not athlete_services(athlete_id).training:
        abort(404)
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(401)
    block = (
        TrainingBlock.query.filter_by(athlete_id=athlete_id, status="active")
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    logs = (
        TrainingSessionLog.query.filter_by(athlete_id=athlete_id)
        .filter(TrainingSessionLog.session_id.is_not(None))
        .all()
    )
    logs_by_session = {item.session_id: item for item in logs}
    today = datetime.now(UTC).date()
    schedule = project_training_schedule(block, logs_by_session, today=today)
    return render_template(
        "athletes/programme.html",
        athlete=athlete,
        block=block,
        logs_by_session=logs_by_session,
        schedule=schedule,
        schedule_by_session={item.session.id: item for item in schedule.sessions},
        today=today,
        next_session_id=(schedule.next_session.session.id if schedule.next_session else None),
        current_week_id=(schedule.current_week.id if schedule.current_week else None),
    )


@athletes_bp.route(
    "/athlete/programme/sessions/<int:session_id>", methods=["GET", "POST"]
)
def programme_session(session_id: int):
    athlete_id = _signed_in_athlete_id()
    if not athlete_services(athlete_id).training:
        abort(404)
    training_session = db.session.get(TrainingSession, session_id)
    if training_session is None or training_session.week.block.athlete_id != athlete_id:
        abort(404)
    if training_session.week.block.status != "active":
        abort(404)
    log = assigned_log(athlete_id, training_session.id)
    errors: tuple[str, ...] = ()
    if request.method == "POST":
        result = save_training_session(training_session, athlete_id, request.form)
        log, errors = result.log, result.errors
        if not errors:
            message = (
                "Session finished. Your training is saved."
                if log is not None and log.status == "completed"
                else "Progress saved."
            )
            flash(message, "success")
            return redirect(
                url_for("athletes.programme_session", session_id=training_session.id)
            )
    results_by_set = (
        {(item.exercise_position, item.set_order): item for item in log.results}
        if log is not None
        else {}
    )
    return render_template(
        "athletes/programme_session.html",
        session=training_session,
        week=training_session.week,
        block=training_session.week.block,
        log=log,
        has_v7_slots=any(item.slot_role for item in training_session.prescriptions),
        results_by_set=results_by_set,
        errors=errors,
        warmup_steps=athlete_warmup(athlete_id, training_session.id),
    ), (400 if errors else 200)


@athletes_bp.get("/athletes/<int:athlete_id>/training-sessions/<int:log_id>")
def coach_training_session(athlete_id: int, log_id: int):
    user = g.get("current_user")
    if user is not None and getattr(user, "role", None) == "athlete":
        abort(403)
    athlete = db.session.get(Athlete, athlete_id)
    log = db.session.get(TrainingSessionLog, log_id)
    if athlete is None or log is None or log.athlete_id != athlete.id:
        abort(404)
    return render_template(
        "athletes/coach_training_session.html", athlete=athlete, log=log
    )


def _optional_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    return float(value)


def _optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    return int(value)


def _required_score(name: str) -> int:
    value = request.form.get(name, "").strip()

    if not value:
        raise ValueError(name)

    score = int(value)

    if score < 1 or score > 10:
        raise ValueError(name)

    return score


def _parse_date(name: str, errors: dict[str, str]) -> date | None:
    value = request.form.get(name, "").strip()
    # Compatibility for established API/form clients; the browser form always
    # supplies an explicit required date.
    if not value:
        return datetime.now(UTC).date()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors[name] = "Enter a valid check-in date."
        return None
    if parsed > datetime.now(UTC).date():
        errors[name] = "Check-in date cannot be in the future."
    return parsed


def _number(name: str, label: str, minimum: float, maximum: float, errors: dict[str, str], *, integer: bool = False):
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        result = int(value) if integer else float(value)
    except ValueError:
        errors[name] = f"{label} must be a number."
        return None
    if result < minimum or result > maximum:
        errors[name] = f"{label} must be between {minimum:g} and {maximum:g}."
    return result


def _nutrition_form_values() -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    values = {
        "checkin_date": _parse_date("checkin_date", errors),
        "bodyweight_kg": _number("bodyweight_kg", "Average bodyweight", 25, 350, errors),
        "calorie_target": _number("calorie_target", "Calorie target", 500, 10000, errors, integer=True),
        "average_calories": _number("average_calories", "Average calorie intake", 0, 10000, errors, integer=True),
        "protein_target_g": _number("protein_target_g", "Protein target", 0, 500, errors, integer=True),
        "average_protein_g": _number("average_protein_g", "Average protein", 0, 500, errors, integer=True),
        "carbohydrate_target_g": _number("carbohydrate_target_g", "Carbohydrate target", 0, 1000, errors, integer=True),
        "average_carbohydrate_g": _number("average_carbohydrate_g", "Average carbohydrate", 0, 1000, errors, integer=True),
        "fat_target_g": _number("fat_target_g", "Fat target", 0, 400, errors, integer=True),
        "average_fat_g": _number("average_fat_g", "Average fat", 0, 400, errors, integer=True),
        "average_fibre_g": _number("average_fibre_g", "Average fibre", 0, 150, errors),
        "average_fluid_l": _number("average_fluid_l", "Average fluid", 0, 15, errors),
        "average_steps": _number("average_steps", "Average steps", 0, 100000, errors, integer=True),
        "average_sleep_hours": _number("average_sleep_hours", "Average sleep", 0, 24, errors),
    }
    for name in ("nutrition_adherence", "hunger", "energy", "sleep_quality", "digestion"):
        try:
            values[name] = _required_score(name)
        except (TypeError, ValueError):
            errors[name] = "Choose a score from 1 to 10."
    return values, errors


@athletes_bp.get("/athletes")
def athlete_list():
    athletes = Athlete.query.order_by(
        Athlete.status.asc(),
        Athlete.last_name.asc(),
        Athlete.first_name.asc(),
    ).all()

    return render_template(
        "athletes/list.html",
        athletes=athletes,
        errors={},
        form={},
    )


@athletes_bp.post("/athletes")
def create_athlete():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()

    form = request.form
    if not first_name or not last_name or not email:
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"form": "First name, last name and email are required."}, form=form,
        ), 400

    if Athlete.query.filter(db.func.lower(Athlete.email) == email).first() is not None:
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"email": "An athlete with this email already exists."}, form=form,
        ), 400

    athlete = Athlete(
        first_name=first_name,
        last_name=last_name,
        email=email,
        instagram=request.form.get("instagram", "").strip() or None,
        bodyweight_kg=_optional_float(request.form.get("bodyweight_kg")),
        weight_class=request.form.get("weight_class", "").strip() or None,
        federation=request.form.get("federation", "").strip() or None,
        next_competition=request.form.get("next_competition", "").strip() or None,
    )

    db.session.add(athlete)
    db.session.add(
        AthleteCheckinSettings(
            athlete=athlete,
            training_enabled=True,
            nutrition_enabled=False,
            workflow_active=True,
            checkin_day=0,
        )
    )

    service_effective_at = datetime.now(UTC).replace(tzinfo=None)
    db.session.add_all(
        [
            ClientServiceChange(
                athlete=athlete,
                service="training",
                value="yes",
                effective_at=service_effective_at,
            ),
            ClientServiceChange(
                athlete=athlete,
                service="nutrition",
                value="no",
                effective_at=service_effective_at,
            ),
            ClientServiceChange(
                athlete=athlete,
                service="meet_day",
                value="no",
                effective_at=service_effective_at,
            ),
            ClientServiceChange(
                athlete=athlete,
                service="video_review",
                value="none",
                effective_at=service_effective_at,
            ),
        ]
    )
    try:
        db.session.commit()
    except IntegrityError:
        # The unique constraint closes the race after the friendly pre-check.
        db.session.rollback()
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"email": "An athlete with this email already exists."}, form=form,
        ), 400

    return redirect(
        url_for(
            "athletes.client_onboarding",
            athlete_id=athlete.id,
        )
    )


def _onboarding_athlete(athlete_id: int) -> Athlete:
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)
    return athlete


@athletes_bp.get("/athletes/<int:athlete_id>/onboarding")
@roles_required(UserRole.COACH)
def client_onboarding(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    return render_template(
        "athletes/onboarding.html",
        onboarding=build_client_onboarding(athlete),
        client_services=resolved_client_services(athlete.id),
        weekdays=enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")),
    )


@athletes_bp.post("/athletes/<int:athlete_id>/onboarding/invite")
@roles_required(UserRole.COACH)
def onboarding_invite(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    try:
        require_current(build_client_onboarding(athlete), "invite")
        create_invitation(
            athlete,
            activation_url=_account_link(AccountTokenPurpose.INVITATION),
            lifetime=current_app.config["ACCOUNT_INVITATION_LIFETIME"],
        )
    except (AccountLifecycleError, ValueError) as exc:
        abort(409, description=str(exc))
    flash("Invitation issued. Onboarding will continue when the athlete activates their account.", "success")
    return redirect(url_for("athletes.client_onboarding", athlete_id=athlete.id))


def _replace_onboarding_fact(athlete: Athlete, fact_type: str, value: object) -> None:
    previous = (
        AthleteStateFact.query.filter_by(athlete_id=athlete.id, fact_type=fact_type)
        .order_by(AthleteStateFact.recorded_at.desc(), AthleteStateFact.id.desc())
        .first()
    )
    record_fact(
        athlete_id=athlete.id,
        fact_type=fact_type,
        value=value,
        source_type="coach",
        recorded_by=getattr(g.get("current_user"), "email", None),
        source_ref="client_onboarding",
        supersedes=previous,
    )


@athletes_bp.post("/athletes/<int:athlete_id>/onboarding/goals")
@roles_required(UserRole.COACH)
def onboarding_goals(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    try:
        require_current(build_client_onboarding(athlete), "goals")
    except ValueError as exc:
        abort(409, description=str(exc))
    primary_goal = request.form.get("primary_goal", "").strip()
    success_definition = request.form.get("success_definition", "").strip()
    if not primary_goal or not success_definition or len(primary_goal) > 1000 or len(success_definition) > 1000:
        abort(400, description="Enter a primary goal and a concise definition of success.")
    _replace_onboarding_fact(athlete, "onboarding_goals", {
        "primary_goal": primary_goal,
        "success_definition": success_definition,
    })
    db.session.commit()
    return redirect(url_for("athletes.client_onboarding", athlete_id=athlete.id))


@athletes_bp.post("/athletes/<int:athlete_id>/onboarding/services")
@roles_required(UserRole.COACH)
def onboarding_services(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    try:
        require_current(build_client_onboarding(athlete), "services")
    except ValueError as exc:
        abort(409, description=str(exc))
    allowed = {key: choices for key, _label, choices in SERVICE_DEFINITIONS}
    values = {key: request.form.get(key, "") for key in allowed}
    if any(values[key] not in allowed[key] for key in allowed):
        abort(400, description="Choose a valid state for every client service.")
    now = datetime.now(UTC).replace(tzinfo=None)
    current = {item["key"]: item["value"] for item in resolved_client_services(athlete.id)}
    for key, value in values.items():
        if current[key] != value:
            db.session.add(ClientServiceChange(
                athlete_id=athlete.id, service=key, value=value, effective_at=now,
                changed_by_user_id=getattr(g.get("current_user"), "id", None),
            ))
    _replace_onboarding_fact(athlete, "onboarding_services", values)
    db.session.commit()
    return redirect(url_for("athletes.client_onboarding", athlete_id=athlete.id))


@athletes_bp.post("/athletes/<int:athlete_id>/onboarding/programme")
@roles_required(UserRole.COACH)
def onboarding_programme(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    onboarding = build_client_onboarding(athlete)
    try:
        require_current(onboarding, "programme")
    except ValueError as exc:
        abort(409, description=str(exc))
    block = db.session.get(TrainingBlock, request.form.get("block_id", type=int))
    if block is None or block.athlete_id != athlete.id:
        abort(404)
    try:
        activate(block)
        db.session.commit()
    except BlockActivationError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    return redirect(url_for("athletes.client_onboarding", athlete_id=athlete.id))


@athletes_bp.post("/athletes/<int:athlete_id>/onboarding/check-in")
@roles_required(UserRole.COACH)
def onboarding_checkin(athlete_id: int):
    athlete = _onboarding_athlete(athlete_id)
    try:
        require_current(build_client_onboarding(athlete), "checkin")
    except ValueError as exc:
        abort(409, description=str(exc))
    checkin_day = request.form.get("checkin_day", type=int)
    if checkin_day not in range(7):
        abort(400, description="Choose a valid check-in day.")
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()
    if settings is None:
        settings = AthleteCheckinSettings(athlete=athlete)
        db.session.add(settings)
    profile = effective_client_service_profile(athlete.id)
    settings.training_enabled = profile.training_coaching_enabled and request.form.get("training_enabled") == "1"
    settings.nutrition_enabled = profile.nutrition_coaching_enabled and request.form.get("nutrition_enabled") == "1"
    settings.workflow_active = True
    settings.checkin_day = checkin_day
    if not settings.has_enabled_modules:
        abort(400, description="Enable at least one entitled check-in module.")
    _replace_onboarding_fact(athlete, "onboarding_checkin_setup", {
        "checkin_day": checkin_day,
        "training_enabled": settings.training_enabled,
        "nutrition_enabled": settings.nutrition_enabled,
    })
    db.session.commit()
    flash("Onboarding complete. The client is ready to start.", "success")
    return redirect(url_for("athletes.client_onboarding", athlete_id=athlete.id))


@athletes_bp.get("/athletes/<int:athlete_id>")
def athlete_dashboard(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    raw_block_id = request.args.get("block") or request.args.get("block_id")
    block_id = None
    if raw_block_id:
        try:
            block_id = int(raw_block_id)
        except ValueError:
            abort(400, description="Choose a valid training block.")

    performance_decisions = build_performance_decisions(
        athlete.id,
        as_of=datetime.now(UTC).date(),
        block_id=block_id,
    )
    if performance_decisions is None:
        abort(404)

    try:
        performance = get_coach_athlete_performance(
            athlete.id,
            block_id=block_id,
        )
    except LookupError:
        abort(404)

    checkins = NutritionCheckIn.query.filter_by(athlete_id=athlete.id).all()

    checkins.sort(key=lambda checkin: (checkin.checkin_date, checkin.id), reverse=True)
    for index, checkin in enumerate(checkins):
        older = checkins[index + 1] if index + 1 < len(checkins) else None
        checkin.weekly_bodyweight_change_kg = (
            round(checkin.bodyweight_kg - older.bodyweight_kg, 2)
            if older is not None
            and checkin.bodyweight_kg is not None
            and older.bodyweight_kg is not None
            else None
        )

    latest_checkin = checkins[0] if checkins else None
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()
    if settings is None:
        settings = AthleteCheckinSettings(
            athlete_id=athlete.id,
            training_enabled=True,
            nutrition_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )

    return render_template(
        "athletes/dashboard.html",
        athlete=athlete,
        performance_decisions=performance_decisions,
        performance=performance,
        performance_blocks=(
            TrainingBlock.query.filter_by(athlete_id=athlete.id)
            .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
            .all()
        ),
        checkins=checkins,
        latest_checkin=latest_checkin,
        checkin_settings=settings,
        nutrition_coaching_enabled=nutrition_coaching_enabled(athlete.id),
        weekly_checkin_due=settings.is_due_on(datetime.now(UTC).date()),
        imported_nutrition=_summary(
            athlete.id,
            datetime.now(UTC).date() - timedelta(days=6),
            datetime.now(UTC).date(),
        ),
        training_logs=(
            TrainingSessionLog.query.filter_by(
                athlete_id=athlete.id,
                status="completed",
            )
            .order_by(TrainingSessionLog.completed_at.desc())
            .all()
        ),
        account_state=account_state(athlete),
        invitation=latest_token(athlete.id, AccountTokenPurpose.INVITATION),
        password_reset=latest_token(athlete.id, AccountTokenPurpose.PASSWORD_RESET),
        client_services=resolved_client_services(athlete.id),
        external_reviews=(
            ExternalCoachingReview.query.filter_by(athlete_id=athlete.id)
            .order_by(ExternalCoachingReview.reviewed_at.desc(), ExternalCoachingReview.id.desc())
            .all()
        ),
        external_review_observations=(
            CoachTechnicalObservation.query.filter_by(athlete_id=athlete.id)
            .order_by(CoachTechnicalObservation.observed_on.desc(), CoachTechnicalObservation.id.desc())
            .all()
        ),
    )


@athletes_bp.post("/athletes/<int:athlete_id>/services")
@roles_required(UserRole.COACH)
def update_client_services(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)

    effective_date = request.form.get("effective_date", "").strip()
    try:
        effective_at = (
            datetime.strptime(effective_date, "%Y-%m-%d")
            if effective_date
            else datetime.now(UTC).replace(tzinfo=None)
        )
    except ValueError:
        abort(400, description="Choose a valid effective date.")

    current = {item["key"]: item["value"] for item in resolved_client_services(athlete.id)}
    allowed = {key: choices for key, _label, choices in SERVICE_DEFINITIONS}
    changed = 0
    for service, choices in allowed.items():
        value = request.form.get(service, "")
        if value not in choices:
            abort(400, description="Choose a valid state for every client service.")
        if value == current[service]:
            continue
        db.session.add(
            ClientServiceChange(
                athlete_id=athlete.id,
                service=service,
                value=value,
                effective_at=effective_at,
                changed_by_user_id=getattr(g.get("current_user"), "id", None),
            )
        )
        changed += 1
    db.session.commit()
    flash(
        "Client services updated." if changed else "No service changes were needed.",
        "success",
    )
    return redirect(url_for("athletes.athlete_dashboard", athlete_id=athlete.id) + "#client-services")


def _account_link(purpose: AccountTokenPurpose) -> str:
    endpoint = url_for("auth.account_token", purpose=purpose.value) + "#{token}"
    base_url = current_app.config.get("ACCOUNT_PUBLIC_BASE_URL")
    if base_url:
        link = str(base_url).rstrip("/") + endpoint
    else:
        link = request.url_root.rstrip("/") + endpoint
    return link


def _account_action_result(athlete: Athlete, issued):
    state = issued.record.delivery_state
    manual_url = None
    if state in {DeliveryState.NOT_CONFIGURED, DeliveryState.FAILED}:
        purpose = AccountTokenPurpose(issued.record.purpose)
        manual_url = _account_link(purpose).format(token=issued.raw_token)
    return render_template(
        "athletes/account_delivery.html",
        athlete=athlete,
        token=issued.record,
        manual_url=manual_url,
    )


@athletes_bp.post("/athletes/<int:athlete_id>/account/invite")
@roles_required(UserRole.COACH)
def invite_account(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)
    if request.form.get("email", "").strip().casefold() != athlete.email.casefold():
        abort(400, description="Confirm the athlete email before sending an invitation.")
    try:
        issued = create_invitation(
            athlete,
            activation_url=_account_link(AccountTokenPurpose.INVITATION),
            lifetime=current_app.config["ACCOUNT_INVITATION_LIFETIME"],
        )
    except AccountLifecycleError as exc:
        abort(409, description=str(exc))
    return _account_action_result(athlete, issued)


@athletes_bp.post("/athletes/<int:athlete_id>/account/password-reset")
@roles_required(UserRole.COACH)
def create_account_password_reset(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)
    try:
        issued = create_password_reset(
            athlete,
            reset_url=_account_link(AccountTokenPurpose.PASSWORD_RESET),
            lifetime=current_app.config["ACCOUNT_RESET_LIFETIME"],
        )
    except AccountLifecycleError as exc:
        abort(409, description=str(exc))
    return _account_action_result(athlete, issued)


@athletes_bp.post("/athletes/<int:athlete_id>/account/<purpose>/revoke")
@roles_required(UserRole.COACH)
def revoke_account_token(athlete_id: int, purpose: str):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)
    try:
        token_purpose = AccountTokenPurpose(purpose)
    except ValueError:
        abort(404)
    revoke_tokens(athlete.id, token_purpose)
    flash(f"{token_purpose.value.replace('_', ' ').title()} link revoked.", "success")
    return redirect(url_for("athletes.athlete_dashboard", athlete_id=athlete.id))


@athletes_bp.get("/athletes/<int:athlete_id>/nutrition-checkins/new")
def nutrition_checkin_form(athlete_id: int):
    if g.get("current_user") is not None and g.current_user.role == "athlete":
        if not athlete_services(athlete_id).nutrition:
            abort(404)
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)
    if not nutrition_coaching_enabled(athlete):
        abort(403)

    return render_template(
        "athletes/nutrition_checkin.html",
        athlete=athlete,
        errors={},
        form={"checkin_date": datetime.now(UTC).date().isoformat()},
        today=datetime.now(UTC).date().isoformat(),
    )


@athletes_bp.post("/athletes/<int:athlete_id>/nutrition-checkins")
def create_nutrition_checkin(athlete_id: int):
    if g.get("current_user") is not None and g.current_user.role == "athlete":
        if not athlete_services(athlete_id).nutrition:
            abort(404)
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)
    if not nutrition_coaching_enabled(athlete):
        abort(403)

    values, errors = _nutrition_form_values()
    if errors:
        return (
            render_template(
                "athletes/nutrition_checkin.html",
                athlete=athlete,
                errors=errors,
                form=request.form,
                today=datetime.now(UTC).date().isoformat(),
            ),
            400,
        )
    checkin = NutritionCheckIn(
        athlete=athlete,
        **values,
        stress=5,
        training_performance=values["energy"],
        wins=request.form.get("wins", "").strip() or None,
        challenges=request.form.get("challenges", "").strip() or None,
        questions=request.form.get("questions", "").strip() or None,
    )

    if checkin.bodyweight_kg is not None:
        athlete.bodyweight_kg = checkin.bodyweight_kg

    db.session.add(checkin)
    db.session.commit()

    if g.get("current_user") is not None and g.current_user.role == "athlete":
        return redirect(url_for("athletes.dashboard"))
    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete.id,
        )
    )


@athletes_bp.post(
    "/athletes/<int:athlete_id>/nutrition-checkins/<int:checkin_id>/review"
)
def review_nutrition_checkin(athlete_id: int, checkin_id: int):
    if not nutrition_coaching_enabled(athlete_id):
        abort(403)
    checkin = NutritionCheckIn.query.filter_by(
        id=checkin_id,
        athlete_id=athlete_id,
    ).first_or_404()

    response = request.form.get("coach_response", "").strip()
    if len(response) > 5000:
        abort(400, description="Coach response must be 5,000 characters or fewer.")
    checkin.coach_response = response or None
    checkin.reviewed = request.form.get("review_status", "reviewed") == "reviewed"
    checkin.reviewed_at = datetime.now(UTC) if checkin.reviewed else None

    db.session.commit()

    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete_id,
        )
    )
