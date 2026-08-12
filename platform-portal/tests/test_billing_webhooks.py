import pytest

from portal.billing.provider import FakeBillingProvider, ProviderEvent
from portal.billing.webhooks import (
    EventPayloadMismatch,
    InMemoryWebhookEventStore,
    WebhookProcessor,
)


def event(payload=b'{"status":"active"}'):
    return ProviderEvent("fake", "event-123", "subscription.updated", payload)


def test_webhook_event_is_applied_only_once():
    processor = WebhookProcessor(InMemoryWebhookEventStore())
    handled = []

    assert processor.process(event(), handled.append) is True
    assert processor.process(event(), handled.append) is False
    assert handled == [event()]


def test_failed_handler_releases_event_for_deterministic_retry():
    processor = WebhookProcessor(InMemoryWebhookEventStore())
    attempts = 0

    def handler(_event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient failure")

    with pytest.raises(RuntimeError, match="transient"):
        processor.process(event(), handler)
    assert processor.process(event(), handler) is True
    assert attempts == 2


def test_same_provider_event_id_with_changed_payload_is_rejected():
    processor = WebhookProcessor(InMemoryWebhookEventStore())
    processor.process(event(), lambda _: None)

    with pytest.raises(EventPayloadMismatch, match="different payload"):
        processor.process(event(b'{"status":"cancelled"}'), lambda _: None)


def test_provider_names_are_part_of_idempotency_key():
    processor = WebhookProcessor(InMemoryWebhookEventStore())
    handled = []
    first = event()
    second = ProviderEvent("another-fake", first.event_id, first.event_type, first.payload)
    assert processor.process(first, handled.append)
    assert processor.process(second, handled.append)
    assert handled == [first, second]


def test_fake_provider_decodes_without_network_or_secrets():
    decoded = event()
    provider = FakeBillingProvider(events={(b"body", "test-signature"): decoded})
    assert provider.decode_event(b"body", "test-signature") == decoded
