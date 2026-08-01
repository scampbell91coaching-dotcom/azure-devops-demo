from flask import Blueprint, render_template

views_bp = Blueprint("views", __name__)


@views_bp.get("/")
def overview():
    return render_template("overview.html", page="overview")


@views_bp.get("/infrastructure")
def infrastructure():
    return render_template("infrastructure.html", page="infrastructure")


@views_bp.get("/security")
def security():
    return render_template("security.html", page="security")


@views_bp.get("/performance")
def performance():
    return render_template("performance.html", page="performance")


@views_bp.get("/gitops")
def gitops():
    return render_template("gitops.html", page="gitops")


@views_bp.get("/observability")
def observability():
    return render_template("observability.html", page="observability")


@views_bp.get("/resilience")
def resilience():
    return render_template("resilience.html", page="resilience")


@views_bp.get("/history")
def history():
    return render_template("history.html", page="history")
