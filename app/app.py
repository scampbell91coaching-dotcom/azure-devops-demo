import os
import socket

from azure.monitor.opentelemetry import configure_azure_monitor


def configure_monitoring() -> None:
    """Enable Azure Monitor when a connection string is available."""
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        configure_azure_monitor()


# Configure instrumentation before importing Flask.
configure_monitoring()

from flask import Flask, jsonify  # noqa: E402


def create_app() -> Flask:
    flask_app = Flask(__name__)

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

    return flask_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
