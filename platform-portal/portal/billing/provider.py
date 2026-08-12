"""Payment-provider port and a deterministic test adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .entitlements import SubscriptionState


@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    event_id: str
    event_type: str
    payload: bytes


@dataclass(frozen=True)
class ProviderSubscription:
    customer_id: str
    subscription_id: str
    plan_identifier: str
    state: SubscriptionState


class BillingProvider(Protocol):
    name: str

    def subscription(self, subscription_id: str) -> ProviderSubscription: ...

    def decode_event(self, payload: bytes, signature: str) -> ProviderEvent: ...


class FakeBillingProvider:
    """No-I/O adapter configured entirely by test fixtures."""

    name = "fake"

    def __init__(
        self,
        subscriptions: Mapping[str, ProviderSubscription] | None = None,
        events: Mapping[tuple[bytes, str], ProviderEvent] | None = None,
    ) -> None:
        self._subscriptions = dict(subscriptions or {})
        self._events = dict(events or {})

    def subscription(self, subscription_id: str) -> ProviderSubscription:
        return self._subscriptions[subscription_id]

    def decode_event(self, payload: bytes, signature: str) -> ProviderEvent:
        return self._events[(payload, signature)]
