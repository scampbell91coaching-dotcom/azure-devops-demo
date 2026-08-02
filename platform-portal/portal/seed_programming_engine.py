from __future__ import annotations

from .extensions import db
from .models.exercise_library import (
    DayTemplate,
    DayTemplateExercise,
    Exercise,
)

EXERCISES = [
    {
        "name": "Competition Squat",
        "movement": "squat",
        "category": "competition",
        "fatigue_rating": 5,
        "default_sets": 1,
        "default_reps": "3",
        "default_rpe": 7,
        "default_rest_seconds": 240,
    },
    {
        "name": "Competition Bench Press",
        "movement": "bench",
        "category": "competition",
        "fatigue_rating": 4,
        "default_sets": 1,
        "default_reps": "4",
        "default_rpe": 7,
        "default_rest_seconds": 180,
    },
    {
        "name": "Competition Deadlift",
        "movement": "deadlift",
        "category": "competition",
        "fatigue_rating": 5,
        "default_sets": 1,
        "default_reps": "3",
        "default_rpe": 7,
        "default_rest_seconds": 240,
    },
]

TEMPLATES = {
    "S": ["Competition Squat"],
    "B": ["Competition Bench Press"],
    "D": ["Competition Deadlift"],
    "SB": ["Competition Squat", "Competition Bench Press"],
    "BD": ["Competition Bench Press", "Competition Deadlift"],
    "SBD": [
        "Competition Squat",
        "Competition Bench Press",
        "Competition Deadlift",
    ],
}


def seed_programming_engine() -> None:
    by_name: dict[str, Exercise] = {}

    for values in EXERCISES:
        exercise = Exercise.query.filter_by(name=values["name"]).first()

        if exercise is None:
            exercise = Exercise(**values)
            db.session.add(exercise)
            db.session.flush()

        by_name[exercise.name] = exercise

    for code, exercise_names in TEMPLATES.items():
        template = DayTemplate.query.filter_by(code=code).first()

        if template is None:
            template = DayTemplate(
                code=code,
                name=_template_name(code),
                description=f"{_template_name(code)} day",
            )
            db.session.add(template)
            db.session.flush()

        if not template.exercises:
            for position, exercise_name in enumerate(
                exercise_names,
                start=1,
            ):
                exercise = by_name[exercise_name]
                template.exercises.append(
                    DayTemplateExercise(
                        exercise=exercise,
                        position=position,
                        sets=exercise.default_sets,
                        reps=exercise.default_reps,
                        rpe=exercise.default_rpe,
                    )
                )

    db.session.commit()


def _template_name(code: str) -> str:
    names = {
        "S": "Squat",
        "B": "Bench",
        "D": "Deadlift",
        "SB": "Squat + Bench",
        "BD": "Bench + Deadlift",
        "SBD": "Squat + Bench + Deadlift",
    }
    return names[code]
