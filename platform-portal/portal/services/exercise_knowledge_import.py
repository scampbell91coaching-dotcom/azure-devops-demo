from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click
from flask import Flask

from ..extensions import db
from ..models.exercise_library import Exercise

VALID_MOVEMENTS = {"squat", "bench", "deadlift", "accessory", "warmup"}
VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
VALID_COMPETITION_RELEVANCE = {"direct", "high", "moderate", "low", "none"}
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
        raise TypeError("Exercise intelligence payload must contain an exercises list.")

    version = payload.get("schema_version")
    if not _is_integer_at_least(version, 1):
        raise ValueError("Exercise intelligence payload has an invalid schema_version.")

    return import_exercise_knowledge(records, catalogue_version=version)


def import_exercise_knowledge(
    records: Sequence[object],
    *,
    catalogue_version: int = 1,
) -> ExerciseImportResult:
    """Upsert validated knowledge records by canonical exercise name."""

    inserted = updated = skipped = invalid = 0
    seen_identities: set[str] = set()
    existing_by_identity = _existing_identity_map()

    for record in records:
        values = _validated_values(record, catalogue_version=catalogue_version)
        if values is None:
            invalid += 1
            continue

        identities = {_identity(values["name"])} | {
            _identity(alias) for alias in json.loads(values["aliases"])
        }
        if seen_identities.intersection(identities):
            invalid += 1
            continue
        seen_identities.update(identities)

        matches = {
            existing_by_identity[key]
            for key in identities
            if key in existing_by_identity
        }
        if len(matches) > 1:
            invalid += 1
            continue
        exercise = next(iter(matches), None)
        if exercise is None:
            exercise = Exercise(**values)
            db.session.add(exercise)
            db.session.flush()
            inserted += 1
        elif _apply_values(exercise, values):
            updated += 1
        else:
            skipped += 1

        for key in identities:
            existing_by_identity[key] = exercise

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


def _validated_values(
    record: object, *, catalogue_version: int
) -> dict[str, Any] | None:
    if not isinstance(record, Mapping):
        return None

    name = _required_string(record.get("name"), maximum_length=160)
    movement = _required_string(record.get("movement"), maximum_length=40)
    family = _required_string(record.get("family"), maximum_length=120)
    category = _required_string(record.get("category"), maximum_length=60)
    equipment = _required_string(record.get("equipment"), maximum_length=120)
    aliases = _validated_aliases(record.get("aliases"), canonical_name=name)
    fatigue_rating = record.get("fatigue_rating")
    occurrence_count = record.get("occurrences")
    default_sets = record.get("default_sets")
    default_reps = _required_string(record.get("default_reps"), maximum_length=40)
    default_rpe = record.get("default_rpe")
    default_rest_seconds = record.get("default_rest_seconds")
    primary_muscles = _validated_string_list(record.get("primary_muscles"), minimum_items=1)
    secondary_muscles = _validated_string_list(record.get("secondary_muscles"))
    coaching_cues = _validated_string_list(record.get("coaching_cues"), minimum_items=2)
    common_mistakes = _validated_string_list(record.get("common_mistakes"), minimum_items=1)
    regressions = _validated_string_list(record.get("regressions"), minimum_items=1)
    progressions = _validated_string_list(record.get("progressions"), minimum_items=1)
    prescription_styles = _validated_string_list(record.get("prescription_styles"), minimum_items=1)
    goal = _required_string(record.get("goal"), maximum_length=120)
    difficulty = _required_string(record.get("difficulty"), maximum_length=20)
    setup = _required_string(record.get("setup"), maximum_length=2000)
    execution = _required_string(record.get("execution"), maximum_length=2000)
    cautions = _required_string(record.get("cautions"), maximum_length=2000)
    relevance = _required_string(record.get("competition_relevance"), maximum_length=40)
    rep_ranges = _required_string(record.get("rep_ranges"), maximum_length=80)
    warmup_suitable = record.get("warmup_suitable")
    accessory_suitable = record.get("accessory_suitable")
    active = record.get("active")

    if (
        name is None
        or movement not in VALID_MOVEMENTS
        or family is None
        or category is None
        or equipment is None
        or aliases is None
        or primary_muscles is None
        or secondary_muscles is None
        or coaching_cues is None
        or common_mistakes is None
        or regressions is None
        or progressions is None
        or prescription_styles is None
        or goal is None
        or difficulty not in VALID_DIFFICULTIES
        or setup is None
        or execution is None
        or cautions is None
        or relevance not in VALID_COMPETITION_RELEVANCE
        or rep_ranges is None
        or not isinstance(warmup_suitable, bool)
        or not isinstance(accessory_suitable, bool)
        or not isinstance(active, bool)
        or not _is_integer_between(fatigue_rating, 1, 5)
        or not _is_integer_at_least(occurrence_count, 0)
        or not _is_integer_between(default_sets, 1, 20)
        or default_reps is None
        or not isinstance(default_rpe, (int, float))
        or isinstance(default_rpe, bool)
        or not 1 <= default_rpe <= 10
        or not _is_integer_between(default_rest_seconds, 0, 1800)
        or len(setup) < 30
        or len(execution) < 30
        or len(cautions) < 30
        or (movement == "warmup" and not warmup_suitable)
        or (movement == "warmup" and accessory_suitable)
        or (category == "competition" and relevance != "direct")
        or (category == "competition" and accessory_suitable)
    ):
        return None

    return {
        "name": name,
        "movement": movement,
        "family": family,
        "category": category,
        "variation": category,
        "equipment": equipment,
        "aliases": json.dumps(aliases),
        "fatigue_rating": fatigue_rating,
        "occurrence_count": occurrence_count,
        "default_sets": default_sets,
        "default_reps": default_reps,
        "default_rpe": float(default_rpe),
        "default_rest_seconds": default_rest_seconds,
        "primary_muscles": ", ".join(primary_muscles),
        "secondary_muscles": ", ".join(secondary_muscles),
        "goal": goal,
        "difficulty": difficulty,
        "setup": setup,
        "execution": execution,
        "coaching_cues": json.dumps(coaching_cues),
        "common_mistakes": json.dumps(common_mistakes),
        "regressions": json.dumps(regressions),
        "progressions": json.dumps(progressions),
        "cautions": cautions,
        "competition_relevance": relevance,
        "prescription_styles": json.dumps(prescription_styles),
        "rep_ranges": rep_ranges,
        "warmup_suitable": warmup_suitable,
        "accessory_suitable": accessory_suitable,
        "active": active,
        "catalogue_version": catalogue_version,
    }


def _required_string(value: object, maximum_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result if result and len(result) <= maximum_length else None


def _validated_aliases(
    value: object, *, canonical_name: str | None = None
) -> list[str] | None:
    if not isinstance(value, list):
        return None

    aliases: list[str] = []
    for alias in value:
        normalised_alias = _required_string(alias, maximum_length=160)
        if normalised_alias is None:
            return None
        if canonical_name is not None and _identity(normalised_alias) == _identity(canonical_name):
            return None
        if _identity(normalised_alias) not in {_identity(item) for item in aliases}:
            aliases.append(normalised_alias)
    return aliases


def _validated_string_list(
    value: object, *, minimum_items: int = 0
) -> list[str] | None:
    items = _validated_aliases(value)
    if (
        items is None
        or not isinstance(value, list)
        or len(items) != len(value)
        or len(items) < minimum_items
    ):
        return None
    return items


def _identity(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value).casefold()
    return re.sub(r"[^a-z0-9]+", " ", normalised).strip()


def _existing_identity_map() -> dict[str, Exercise]:
    identities: dict[str, Exercise] = {}
    for exercise in Exercise.query.order_by(Exercise.id.asc()).all():
        values = [exercise.name]
        if exercise.aliases:
            try:
                aliases = json.loads(exercise.aliases)
                if isinstance(aliases, list):
                    values.extend(alias for alias in aliases if isinstance(alias, str))
            except json.JSONDecodeError:
                pass
        for value in values:
            identities.setdefault(_identity(value), exercise)
    return identities


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
