from __future__ import annotations

from typing import Any

from ..repositories.history_repository import HistoryRepository


class HistoryService:
    def __init__(self, repository: HistoryRepository | None = None) -> None:
        self.repository = repository or HistoryRepository()

    def get_all(self) -> list[dict[str, Any]]:
        return self.repository.list()
