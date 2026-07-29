import os
import socket
import time

from azure.monitor.opentelemetry import configure_azure_monitor
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
        configure_azure_monitor()


# Configure Azure instrumentation before importing Flask.
configure_monitoring()

from flask import Flask, Response, g, jsonify, request  # noqa: E402


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

APPLICATION_INFO = Gauge(
    "flask_application_info",
    "Static information about the running Flask application.",
    ["application"],
)

APPLICATION_INFO.labels(application="flask-web").set(1)


def create_app() -> Flask:
    flask_app = Flask(__name__)

    @flask_app.before_request
    def start_request_timer() -> None:
        g.request_start_time = time.perf_counter()

    @flask_app.after_request
    def record_request_metrics(response: Response) -> Response:
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

        return response

    @flask_app.get("/")
    def home():
        return jsonify(
            status="ok",
            host=socket.gethostname(),
            message="Flask app is running",
        )

    @flask_app.get("/health")
    def health():
        return jsonify(status="healthy"), 200

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
