import json
import logging

from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, use_span
from prometheus_client.parser import text_string_to_metric_families

import app.app as app_module
from app.app import REQUEST_LOGGER, create_app, request_id_from_header


def metric_samples(response, metric_name):
    families = text_string_to_metric_families(response.get_data(as_text=True))
    return [
        sample
        for family in families
        for sample in family.samples
        if sample.name == metric_name
    ]


def test_home_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["status"] == "ok"
    assert payload["message"] == "Flask app is running"
    assert payload["host"]


def test_health_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}
    assert len(response.headers["X-Request-ID"]) == 32


def test_readiness_endpoint_is_distinct_from_health():
    client = create_app().test_client()

    health_response = client.get("/health")
    readiness_response = client.get("/ready")

    assert health_response.get_json() == {"status": "healthy"}
    assert readiness_response.status_code == 200
    assert readiness_response.get_json() == {"status": "ready"}


def test_metrics_expose_bounded_http_and_application_operation_labels():
    client = create_app().test_client()

    client.get("/")
    client.get("/does-not-exist")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")
    request_samples = metric_samples(response, "flask_http_requests_total")
    duration_samples = metric_samples(
        response, "flask_http_request_duration_seconds_count"
    )
    operation_samples = metric_samples(response, "flask_application_operations_total")
    assert any(
        sample.labels == {"method": "GET", "endpoint": "/", "status_code": "200"}
        for sample in request_samples
    )
    assert any(
        sample.labels
        == {"method": "GET", "endpoint": "unmatched", "status_code": "404"}
        for sample in request_samples
    )
    assert any(
        sample.labels == {"method": "GET", "endpoint": "/"}
        for sample in duration_samples
    )
    assert any(
        sample.labels == {"operation": "serve_home", "outcome": "success"}
        for sample in operation_samples
    )
    assert all(
        "does-not-exist" not in sample.labels.values() for sample in request_samples
    )


def test_server_errors_are_counted_and_metrics_scrapes_are_not():
    app = create_app()

    @app.get("/test-unavailable")
    def unavailable():
        return {"status": "unavailable"}, 503

    client = app.test_client()
    client.get("/test-unavailable")
    client.get("/metrics")
    response = client.get("/metrics")

    error_samples = metric_samples(response, "flask_http_request_errors_total")
    request_samples = metric_samples(response, "flask_http_requests_total")
    assert any(
        sample.labels
        == {
            "method": "GET",
            "endpoint": "/test-unavailable",
            "status_code": "503",
        }
        for sample in error_samples
    )
    assert all(sample.labels["endpoint"] != "/metrics" for sample in request_samples)


def test_request_id_accepts_safe_value_and_replaces_untrusted_value():
    assert (
        request_id_from_header("A0B1C2D3-E4F5-6789-ABCD-EF0123456789")
        == "a0b1c2d3-e4f5-6789-abcd-ef0123456789"
    )

    generated = request_id_from_header("unsafe value\nforged")

    assert len(generated) == 32
    assert generated.isalnum()


def test_request_log_links_request_and_trace_without_query_string():
    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = ListHandler()
    REQUEST_LOGGER.addHandler(handler)
    span_context = SpanContext(
        trace_id=0x1234,
        span_id=0x5678,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    try:
        with use_span(NonRecordingSpan(span_context)):
            response = (
                create_app()
                .test_client()
                .get(
                    "/?private=do-not-log",
                    headers={"X-Request-ID": "1234567890abcdef1234567890abcdef"},
                )
            )
    finally:
        REQUEST_LOGGER.removeHandler(handler)

    payload = json.loads(records[-1].getMessage())
    assert response.headers["X-Request-ID"] == "1234567890abcdef1234567890abcdef"
    assert payload["request_id"] == "1234567890abcdef1234567890abcdef"
    assert payload["trace_id"] == "00000000000000000000000000001234"
    assert payload["span_id"] == "0000000000005678"
    assert payload["route"] == "/"
    assert "private" not in records[-1].getMessage()


def test_optional_telemetry_failures_do_not_break_runtime(monkeypatch):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "invalid")
    monkeypatch.setattr(
        app_module,
        "configure_azure_monitor",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    app_module.configure_monitoring()

    monkeypatch.setattr(
        REQUEST_LOGGER,
        "info",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    response = create_app().test_client().get("/")

    assert response.status_code == 200
