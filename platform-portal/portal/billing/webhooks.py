"""Provider-event idempotency boundary independent of HTTP and provider SDKs."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Callable, Protocol

from .provider import ProviderEvent


class ClaimResult(StrEnum):
    CLAIMED = "claimed"
    DUPLICATE = "duplicate"


class EventPayloadMismatch(ValueError):
    pass


class WebhookEventStore(Protocol):
    def claim(self, provider: str, event_id: str, payload_digest: str) -> ClaimResult: ...
    def complete(self, provider: str, event_id: str) -> None: ...
    def fail(self, provider: str, event_id: str) -> None: ...


class WebhookProcessor:
    def __init__(self, store: WebhookEventStore) -> None:
        self._store = store

    def process(self, event: ProviderEvent, handler: Callable[[ProviderEvent], None]) -> bool:
        digest = hashlib.sha256(event.payload).hexdigest()
        if self._store.claim(event.provider, event.event_id, digest) is ClaimResult.DUPLICATE:
            return False
        try:
            handler(event)
        except Exception:
            self._store.fail(event.provider, event.event_id)
            raise
        self._store.complete(event.provider, event.event_id)
        return True


class InMemoryWebhookEventStore:
    """Deterministic contract implementation; failed events may be retried."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], tuple[str, str]] = {}

    def claim(self, provider: str, event_id: str, payload_digest: str) -> ClaimResult:
        key = (provider, event_id)
        existing = self._events.get(key)
        if existing:
            existing_digest, status = existing
            if existing_digest != payload_digest:
                raise EventPayloadMismatch("event ID was reused with a different payload")
            if status in {"processing", "processed"}:
                return ClaimResult.DUPLICATE
        self._events[key] = (payload_digest, "processing")
        return ClaimResult.CLAIMED

    def complete(self, provider: str, event_id: str) -> None:
        digest, _ = self._events[(provider, event_id)]
        self._events[(provider, event_id)] = (digest, "processed")

    def fail(self, provider: str, event_id: str) -> None:
        digest, _ = self._events[(provider, event_id)]
        self._events[(provider, event_id)] = (digest, "failed")
