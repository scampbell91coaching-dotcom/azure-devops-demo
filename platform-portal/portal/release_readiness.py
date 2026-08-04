"""Release-readiness page backed exclusively by generated release evidence."""

from flask import Blueprint, current_app, render_template

release_readiness_bp = Blueprint("release_readiness", __name__)


@release_readiness_bp.get("/release-readiness")
def release_readiness():
    result = current_app.extensions["release_evidence"].load()
    return render_template(
        "release_readiness.html",
        page="release-readiness",
        result=result,
    )
