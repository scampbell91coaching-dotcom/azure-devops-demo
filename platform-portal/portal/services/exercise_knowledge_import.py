from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click
from flask import Flask

from ..extensions import db
from ..models.exercise_library import Exercise

VALID_MOVEMENTS = {"squat", "bench", "deadlift", "accessory", "warmup"}
DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "traditional_strength_intelligence.json"
)


@dataclass(frozen=True)
class ExerciseImportResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def import_exercise_knowledge_file(
    path: Path = DEFAULT_DATA_PATH,
) -> ExerciseImportResult:
    """Load a Traditional Strength intelligence export from ``path``."""

    with path.open(encoding="utf-8") as source:
        payload: object = json.load(source)

    if not isinstance(payload, Mapping):
        raise TypeError("Exercise intelligence payload must be an object.")

    records = payload.get("exercises")
    if not isinstance(records, list):
        raise TypeError(
            "Exercise intelligence payload must contain an exercises list."
        )

    return import_exercise_knowledge(records)


def import_exercise_knowledge(
    records: Sequence[object],
) -> ExerciseImportResult:
    """Upsert validated knowledge records by canonical exercise name."""

    inserted = updated = skipped = invalid = 0
    seen_names: set[str] = set()

    for record in records:
        values = _validated_values(record)
        if values is None or values["name"] in seen_names:
            invalid += 1
            continue
        seen_names.add(values["name"])

        exercise = Exercise.query.filter_by(name=values["name"]).first()
        if exercise is None:
            db.session.add(Exercise(**values))
            inserted += 1
            continue

        if _apply_values(exercise, values):
            updated += 1
        else:
            skipped += 1

    db.session.commit()
    return ExerciseImportResult(inserted, updated, skipped, invalid)


def register_exercise_knowledge_import_command(app: Flask) -> None:
    @app.cli.command("import-exercise-knowledge")
    @click.option(
        "--path",
        "data_path",
        type=click.Path(path_type=Path, exists=True, dir_okay=False),
        default=DEFAULT_DATA_PATH,
        show_default=True,
    )
    def import_exercise_knowledge_command(data_path: Path) -> None:
        """Import the bundled production exercise knowledge dataset."""

        result = import_exercise_knowledge_file(data_path)
        click.echo(json.dumps(result.as_dict(), sort_keys=True))


def _validated_values(record: object) -> dict[str, Any] | None:
    if not isinstance(record, Mapping):
        return None

    name = _required_string(record.get("name"), maximum_length=160)
    movement = _required_string(record.get("movement"), maximum_length=40)
    family = _required_string(record.get("family"), maximum_length=120)
    category = _required_string(record.get("category"), maximum_length=60)
    equipment = _required_string(record.get("equipment"), maximum_length=120)
    aliases = _validated_aliases(record.get("aliases"))
    fatigue_rating = record.get("fatigue_rating")
    occurrence_count = record.get("occurrences")

    if (
        name is None
        or movement not in VALID_MOVEMENTS
        or family is None
        or category is None
        or equipment is None
        or aliases is None
        or not _is_integer_between(fatigue_rating, 1, 5)
        or not _is_integer_at_least(occurrence_count, 0)
    ):
        return None

    return {
        "name": name,
        "movement": movement,
        "family": family,
        "category": category,
        "equipment": equipment,
        "aliases": json.dumps(aliases),
        "fatigue_rating": fatigue_rating,
        "occurrence_count": occurrence_count,
    }


def _required_string(value: object, maximum_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result if result and len(result) <= maximum_length else None


def _validated_aliases(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None

    aliases: list[str] = []
    for alias in value:
        normalised_alias = _required_string(alias, maximum_length=160)
        if normalised_alias is None:
            return None
        if normalised_alias not in aliases:
            aliases.append(normalised_alias)
    return aliases


def _is_integer_between(value: object, minimum: int, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def _is_integer_at_least(value: object, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _apply_values(exercise: Exercise, values: Mapping[str, Any]) -> bool:
    changed = False
    for field, value in values.items():
        if getattr(exercise, field) != value:
            setattr(exercise, field, value)
            changed = True
    return changed
