"""Low-cardinality production telemetry for the coaching portal."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from flask import Response, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS = Counter(
    "flask_http_requests_total",
    "HTTP requests handled by the portal.",
    ("method", "endpoint", "status_code"),
)
HTTP_DURATION = Histogram(
    "flask_http_request_duration_seconds",
    "Portal request duration.",
    ("method", "endpoint"),
)
AUTH_EVENTS = Counter(
    "traditional_strength_auth_events_total",
    "Authentication and authorization outcomes.",
    ("event", "outcome"),
)
TENANT_DENIALS = Counter(
    "traditional_strength_tenant_access_denials_total",
    "Tenant boundary denials without tenant or object identifiers.",
    ("reason",),
)
DEPENDENCY_AVAILABLE = Gauge(
    "traditional_strength_dependency_available",
    "Whether a dependency succeeded during the latest readiness check.",
    ("dependency",),
)

_REQUEST_ID = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)
_LOGGER = logging.getLogger("traditional_strength.request")


def record_auth_event(event: str, outcome: str) -> None:
    AUTH_EVENTS.labels(event=event, outcome=outcome).inc()


def record_tenant_denial(reason: str) -> None:
    TENANT_DENIALS.labels(reason=reason).inc()


def set_dependency_available(dependency: str, available: bool) -> None:
    DEPENDENCY_AVAILABLE.labels(dependency=dependency).set(1 if available else 0)


def _request_id(value: str | None) -> str:
    return value.lower() if value and _REQUEST_ID.fullmatch(value) else uuid.uuid4().hex


def _endpoint() -> str:
    return request.url_rule.rule if request.url_rule else "unmatched"


def init_observability(app) -> None:
    """Register metrics and structured request logging once per app."""

    @app.before_request
    def _start_request() -> None:
        g.observability_started = time.perf_counter()
        g.request_id = _request_id(request.headers.get("X-Request-ID"))

    @app.after_request
    def _record_request(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.get("request_id", uuid.uuid4().hex)
        if request.path == "/metrics":
            return response

        endpoint = _endpoint()
        elapsed = time.perf_counter() - g.get(
            "observability_started", time.perf_counter()
        )
        HTTP_REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, endpoint).observe(elapsed)

        if request.path not in {"/health", "/live", "/ready"}:
            severity = "ERROR" if response.status_code >= 500 else "INFO"
            _LOGGER.log(
                logging.ERROR if severity == "ERROR" else logging.INFO,
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": severity,
                        "event": "http_request_completed",
                        "service": "traditional-strength",
                        "request_id": response.headers["X-Request-ID"],
                        "method": request.method,
                        "route": endpoint,
                        "status_code": response.status_code,
                        "duration_ms": round(elapsed * 1000, 3),
                    },
                    separators=(",", ":"),
                ),
            )
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)
