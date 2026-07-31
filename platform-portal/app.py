from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv("PLATFORM_STATUS_FILE", BASE_DIR / "data" / "platform-status.json"))

app = Flask(__name__)


def load_status() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {
            "score": 0,
            "summary": {"pass": 0, "warn": 0, "fail": 1},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "checks": [
                {
                    "area": "Portal",
                    "name": "Status data",
                    "status": "FAIL",
                    "detail": f"Missing {DATA_FILE}",
                }
            ],
            "platform": {},
            "workload": {},
            "networking": {},
            "availability": {},
            "resilience": {},
            "identity": {},
            "gitops": {},
            "security": {},
            "observability": {},
            "git": {},
        }

    try:
        with DATA_FILE.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "score": 0,
            "summary": {"pass": 0, "warn": 0, "fail": 1},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "checks": [
                {
                    "area": "Portal",
                    "name": "Status data",
                    "status": "FAIL",
                    "detail": f"Unable to read status JSON: {exc}",
                }
            ],
        }

    return data


@app.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.get("/api/status")
def api_status():
    return jsonify(load_status())


@app.get("/")
def overview():
    return render_template("overview.html", page="overview")


@app.get("/infrastructure")
def infrastructure():
    return render_template("infrastructure.html", page="infrastructure")


@app.get("/security")
def security():
    return render_template("security.html", page="security")


@app.get("/performance")
def performance():
    return render_template("performance.html", page="performance")


@app.get("/gitops")
def gitops():
    return render_template("gitops.html", page="gitops")


@app.get("/observability")
def observability():
    return render_template("observability.html", page="observability")


@app.get("/resilience")
def resilience():
    return render_template("resilience.html", page="resilience")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8090")), debug=False)
