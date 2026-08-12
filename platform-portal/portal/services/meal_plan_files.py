"""Tenant-aware authorisation boundary for future meal-plan PDF storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..tenancy import (
    athlete_belongs_to_organisation,
    coach_owns_athlete_in_organisation,
)


@dataclass(frozen=True)
class MealPlanFileMetadata:
    file_id: str
    organisation_id: int
    athlete_id: int
    relative_path: str


class MealPlanFileStore:
    """Open files only after their immutable tenant metadata is authorised."""

    def __init__(self, root: Path):
        self._root = root.resolve()
        self._metadata: dict[str, MealPlanFileMetadata] = {}

    def register(self, metadata: MealPlanFileMetadata) -> None:
        if not athlete_belongs_to_organisation(
            metadata.athlete_id, metadata.organisation_id
        ):
            raise PermissionError("Meal-plan file metadata has invalid Organisation scope")
        self._metadata[metadata.file_id] = metadata

    def open_for_coach(self, file_id: str, coach_user_id: int) -> BinaryIO:
        metadata = self._metadata.get(file_id)
        if metadata is None or coach_owns_athlete_in_organisation(
            coach_user_id, metadata.athlete_id, metadata.organisation_id
        ) is None:
            raise FileNotFoundError(file_id)
        return self._open(metadata)

    def open_for_athlete(self, file_id: str, athlete_id: int) -> BinaryIO:
        metadata = self._metadata.get(file_id)
        if metadata is None or metadata.athlete_id != athlete_id:
            raise FileNotFoundError(file_id)
        if not athlete_belongs_to_organisation(
            athlete_id, metadata.organisation_id
        ):
            raise FileNotFoundError(file_id)
        return self._open(metadata)

    def _open(self, metadata: MealPlanFileMetadata) -> BinaryIO:
        path = (self._root / metadata.relative_path).resolve()
        if self._root not in path.parents:
            raise FileNotFoundError(metadata.file_id)
        return path.open("rb")
