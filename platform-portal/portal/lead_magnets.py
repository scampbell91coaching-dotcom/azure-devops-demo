from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from .extensions import db
from .models.lead_capture import LeadCapture

lead_magnets_bp = Blueprint("lead_magnets", __name__)

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content" / "lead_magnets"


def load_lead_magnet(slug: str) -> dict[str, Any]:
    path = CONTENT_DIR / f"{slug}.json"

    if not path.exists():
        abort(404)

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("slug") != slug:
        abort(404)

    return data


@lead_magnets_bp.get("/guides/<slug>")
def lead_magnet(slug: str):
    content = load_lead_magnet(slug)

    return render_template(
        "lead_magnet.html",
        page="lead-magnet",
        content=content,
        success=request.args.get("success") == "1",
    )


@lead_magnets_bp.post("/api/v1/lead-captures")
def capture_lead():
    first_name = request.form.get("first_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    source_slug = request.form.get("source_slug", "").strip()
    consent = request.form.get("consent") == "on"

    if not first_name or not email or "@" not in email:
        return jsonify({"error": "A valid name and email are required."}), 400

    load_lead_magnet(source_slug)

    lead = LeadCapture(
        first_name=first_name[:100],
        email=email[:320],
        source_slug=source_slug[:120],
        consent=consent,
    )

    db.session.add(lead)
    db.session.commit()

    return redirect(
        url_for(
            "lead_magnets.lead_magnet",
            slug=source_slug,
            success=1,
        )
    )
