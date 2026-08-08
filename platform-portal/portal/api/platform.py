from flask import Blueprint, jsonify

from ..services.platform_status import PlatformStatusService

platform_bp = Blueprint("platform_api", __name__)
service = PlatformStatusService()


@platform_bp.get("/platform")
def platform():
    return jsonify(service.get_status())


@platform_bp.get("/security")
def security():
    d = service.get_status()
    return jsonify(
        {
            "generated_at": d.get("generated_at"),
            "security": d.get("security", {}),
            "identity": d.get("identity", {}),
            "checks": service.checks_for("Security", "Identity", "Networking"),
        }
    )


@platform_bp.get("/gitops")
def gitops():
    d = service.get_status()
    return jsonify(
        {
            "generated_at": d.get("generated_at"),
            "gitops": d.get("gitops", {}),
            "git": d.get("git", {}),
            "checks": service.checks_for("GitOps", "Repository"),
        }
    )


@platform_bp.get("/observability")
def observability():
    return jsonify(service.observability_status())


@platform_bp.get("/resilience")
def resilience():
    d = service.get_status()
    return jsonify(
        {
            "generated_at": d.get("generated_at"),
            "resilience": d.get("resilience", {}),
            "workload": d.get("workload", {}),
            "checks": service.checks_for(
                "Resilience", "Reliability", "Scheduling", "Workload"
            ),
        }
    )
