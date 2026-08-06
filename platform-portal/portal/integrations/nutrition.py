from __future__ import annotations

from typing import Protocol


class NutritionProvider(Protocol):
    name: str

    def preview(self, payload: bytes, filename: str): ...


class OfficialMyFitnessPalProvider:
    """Disabled boundary for a future approved OAuth integration."""

    name = "myfitnesspal_official"

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def authorization_url(self) -> str:
        if not self.enabled:
            raise RuntimeError("Official MyFitnessPal API access is not configured")
        raise NotImplementedError("Implement only after approval and current API docs")
