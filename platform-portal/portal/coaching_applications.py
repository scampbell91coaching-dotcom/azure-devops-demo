from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from .extensions import db
from .models.coaching_application import CoachingApplication

coaching_applications_bp = Blueprint(
    "coaching_applications",
    __name__,
)


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None

    return float(value)


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None

    return int(value)


@coaching_applications_bp.get("/apply")
def application_page():
    return render_template(
        "public/coaching_application.html",
        submitted=request.args.get("submitted") == "1",
        form={},
        errors={},
    )


@coaching_applications_bp.post("/apply")
def submit_application():
    form = request.form.to_dict()
    errors: dict[str, str] = {}

    if form.get("website"):
        return redirect(url_for("coaching_applications.application_page"))

    required_fields = {
        "first_name": "Enter your first name.",
        "last_name": "Enter your last name.",
        "email": "Enter your email address.",
        "country": "Enter your country.",
        "primary_goal": "Tell me what you want to achieve.",
        "biggest_problem": "Tell me what is currently holding you back.",
        "coaching_expectations": "Tell me what you need from a coach.",
    }

    for field, message in required_fields.items():
        if not form.get(field, "").strip():
            errors[field] = message

    email = form.get("email", "").strip()

    if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
        errors["email"] = "Enter a valid email address."

    if form.get("privacy_consent") != "yes":
        errors["privacy_consent"] = "You need to agree before submitting."

    numeric_fields = (
        "age",
        "bodyweight_kg",
        "years_training",
        "squat_kg",
        "bench_kg",
        "deadlift_kg",
        "training_days",
    )

    for field in numeric_fields:
        value = form.get(field, "").strip()

        if not value:
            continue

        try:
            float(value)
        except ValueError:
            errors[field] = "Use a number."

    if errors:
        return (
            render_template(
                "public/coaching_application.html",
                submitted=False,
                form=form,
                errors=errors,
            ),
            400,
        )

    application = CoachingApplication(
        first_name=form["first_name"].strip(),
        last_name=form["last_name"].strip(),
        email=email.lower(),
        instagram=form.get("instagram", "").strip() or None,
        country=form["country"].strip(),
        age=_optional_int(form.get("age")),
        bodyweight_kg=_optional_float(form.get("bodyweight_kg")),
        years_training=_optional_float(form.get("years_training")),
        squat_kg=_optional_float(form.get("squat_kg")),
        bench_kg=_optional_float(form.get("bench_kg")),
        deadlift_kg=_optional_float(form.get("deadlift_kg")),
        next_competition=form.get("next_competition", "").strip() or None,
        current_program=form.get("current_program", "").strip() or None,
        previous_coaching=form.get("previous_coaching", "").strip() or None,
        primary_goal=form["primary_goal"].strip(),
        biggest_problem=form["biggest_problem"].strip(),
        injury_history=form.get("injury_history", "").strip() or None,
        coaching_expectations=form["coaching_expectations"].strip(),
        training_days=_optional_int(form.get("training_days")),
        video_feedback_ready=form.get("video_feedback_ready") == "yes",
        communication_ready=form.get("communication_ready") == "yes",
        minimum_term_ready=form.get("minimum_term_ready") == "yes",
        referral_source=form.get("referral_source", "").strip() or None,
        anything_else=form.get("anything_else", "").strip() or None,
        privacy_consent=True,
    )

    db.session.add(application)
    db.session.commit()

    current_app.logger.info(
        "New coaching application received: id=%s",
        application.id,
    )

    return redirect(
        url_for(
            "coaching_applications.application_page",
            submitted="1",
        )
    )
