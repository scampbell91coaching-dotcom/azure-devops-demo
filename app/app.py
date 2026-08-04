import json
import logging
import os
import re
import socket
import sys
import time
import uuid
from datetime import datetime, timezone

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


def configure_monitoring() -> None:
    """Enable Azure Monitor when a connection string is available."""
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        try:
            configure_azure_monitor()
        except Exception:  # noqa: BLE001 - optional vendor setup must fail open.
            # Telemetry is optional and must not prevent the service starting.
            logging.getLogger(__name__).warning(
                "Azure Monitor setup failed; continuing without telemetry"
            )


# Configure Azure instrumentation before importing Flask.
configure_monitoring()

from flask import Flask, Response, g, jsonify, request  # noqa: I001


REQUEST_COUNT = Counter(
    "flask_http_requests_total",
    "Total number of HTTP requests handled by the Flask application.",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "flask_http_request_duration_seconds",
    "Time spent processing HTTP requests.",
    ["method", "endpoint"],
)

REQUEST_ERRORS = Counter(
    "flask_http_request_errors_total",
    "Total number of HTTP requests that returned a server error.",
    ["method", "endpoint", "status_code"],
)

APPLICATION_OPERATIONS = Counter(
    "flask_application_operations_total",
    "Total number of key application operations.",
    ["operation", "outcome"],
)

APPLICATION_INFO = Gauge(
    "flask_application_info",
    "Static information about the running Flask application.",
    ["application"],
)

APPLICATION_INFO.labels(application="flask-web").set(1)

REQUEST_ID_PATTERN = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)
REQUEST_LOGGER = logging.getLogger("traditional_strength.request")
if not REQUEST_LOGGER.handlers:
    request_log_handler = logging.StreamHandler(sys.stdout)
    request_log_handler.setFormatter(logging.Formatter("%(message)s"))
    REQUEST_LOGGER.addHandler(request_log_handler)
REQUEST_LOGGER.setLevel(logging.INFO)
REQUEST_LOGGER.propagate = False


def request_id_from_header(value: str | None) -> str:
    """Return a safe caller request ID, or create one when absent/invalid."""
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value.lower()
    return uuid.uuid4().hex


def current_trace_fields() -> dict[str, str]:
    """Return W3C trace identifiers when a valid span is available."""
    try:
        span_context = trace.get_current_span().get_span_context()
    except Exception:  # noqa: BLE001 - optional trace context must fail open.
        return {}
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


def emit_request_log(event: dict[str, object]) -> None:
    """Emit structured telemetry without affecting request handling."""
    try:
        REQUEST_LOGGER.info(json.dumps(event, separators=(",", ":")))
    except Exception:  # noqa: BLE001 - optional logging must fail open.
        # Logging is optional; request availability takes precedence.
        return


def create_app() -> Flask:
    flask_app = Flask(__name__)

    @flask_app.before_request
    def start_request_timer() -> None:
        g.request_start_time = time.perf_counter()
        g.request_id = request_id_from_header(request.headers.get("X-Request-ID"))

    @flask_app.after_request
    def record_request_metrics(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.request_id

        # Avoid recording Prometheus scraping itself as application traffic.
        if request.path == "/metrics":
            return response

        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed_seconds = time.perf_counter() - g.request_start_time

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(response.status_code),
        ).inc()

        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(elapsed_seconds)

        if response.status_code >= 500:
            REQUEST_ERRORS.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=str(response.status_code),
            ).inc()

        # Probe and scrape traffic is already represented by dedicated signals.
        if request.path not in {"/health", "/ready"}:
            emit_request_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "INFO",
                    "event": "http_request_completed",
                    "service": "flask-web",
                    "request_id": g.request_id,
                    "method": request.method,
                    "route": endpoint,
                    "status_code": response.status_code,
                    "duration_ms": round(elapsed_seconds * 1000, 3),
                    **current_trace_fields(),
                }
            )

        return response

    @flask_app.get("/")
    def home():
        APPLICATION_OPERATIONS.labels(
            operation="serve_home",
            outcome="success",
        ).inc()
        return jsonify(
            status="ok",
            host=socket.gethostname(),
            message="Flask app is running",
        )

    @flask_app.get("/health")
    def health():
        return jsonify(status="healthy"), 200

    @flask_app.get("/ready")
    def ready():
        return jsonify(status="ready"), 200

    @flask_app.get("/metrics")
    def metrics():
        return Response(
            generate_latest(),
            status=200,
            content_type=CONTENT_TYPE_LATEST,
        )

    return flask_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
