from __future__ import annotations

import hmac
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from functools import wraps
from urllib.parse import unquote_to_bytes, urlsplit

import click
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .models.athlete import Athlete
from .models.user import User, UserRole
from .services.athlete_services import athlete_services

auth_bp = Blueprint("auth", __name__)
_attempts: dict[str, deque[float]] = defaultdict(deque)
_PUBLIC_ENDPOINTS = {
    "auth.account_token",
    "auth.login",
    "health.health",
    "lead_magnets.lead_magnet",
    "lead_magnets.capture_lead",
    "static",
}
_ATHLETE_ENDPOINTS = {
    "athletes.dashboard",
    "athletes.programme",
    "athletes.programme_session",
    "athletes.nutrition_checkin_form",
    "athletes.create_nutrition_checkin",
    "checkins.new",
    "checkins.create",
    "checkins.athlete_history",
    "checkins.athlete_detail",
    "nutrition_imports.index",
    "nutrition_imports.preview",
    "nutrition_imports.commit",
    "nutrition_imports.disconnect",
    "nutrition_prescriptions.athlete_current",
    "meal_plan_delivery.athlete_plan",
    "meal_plan_delivery.athlete_historical_plan",
}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password", method="scrypt")


def _default_destination(user: User) -> str:
    endpoint = (
        "athletes.dashboard"
        if user.user_role == UserRole.ATHLETE
        else "coach_dashboard.index"
    )
    return url_for(endpoint)


def _safe_redirect_target(target: str | None) -> bool:
    if not target or not target.startswith("/"):
        return False

    candidate = target
    for _ in range(5):
        if re.search(r"%(?![0-9a-fA-F]{2})", candidate):
            return False
        try:
            decoded = unquote_to_bytes(candidate).decode("utf-8")
        except UnicodeDecodeError:
            return False
        if (
            not decoded.startswith("/")
            or decoded.startswith("//")
            or "\\" in decoded
            or any(unicodedata.category(char) == "Cc" for char in decoded)
        ):
            return False
        parsed = urlsplit(decoded)
        if parsed.scheme or parsed.netloc:
            return False
        if decoded == candidate:
            return True
        candidate = decoded
    return False


def _client_key(email: str) -> str:
    # Proxy headers are intentionally ignored unless Flask is deployed with a
    # correctly configured ProxyFix. This prevents trivial header spoofing.
    return f"{request.remote_addr or 'unknown'}:{email}"


def _edge_email() -> str:
    """Return a syntactically plausible edge identity for UX hints only.

    The value is never authentication evidence: the application password is
    still required and checked against the selected active user.
    """
    header = current_app.config.get("EDGE_AUTH_EMAIL_HEADER")
    if not isinstance(header, str) or not header:
        return ""
    value = request.headers.get(header, "").strip().casefold()
    if (
        len(value) > 255
        or value.count("@") != 1
        or any(char.isspace() for char in value)
    ):
        return ""
    return value


def _is_rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = int(current_app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"])
    attempts = _attempts[key]
    while attempts and attempts[0] <= now - window:
        attempts.popleft()
    return len(attempts) >= int(current_app.config["LOGIN_RATE_LIMIT_ATTEMPTS"])


def _record_failure(key: str) -> None:
    if len(_attempts) >= 10_000 and key not in _attempts:
        _attempts.pop(next(iter(_attempts)))
    _attempts[key].append(time.monotonic())


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _validate_csrf() -> None:
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not (
        isinstance(expected, str)
        and isinstance(supplied, str)
        and hmac.compare_digest(expected, supplied)
    ):
        abort(400, description="Invalid CSRF token.")


def _requested_athlete_id() -> int | None:
    value = (request.view_args or {}).get("athlete_id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _load_identity() -> None:
    g.current_user = None
    g.session_expired = False
    if current_app.config["AUTHENTICATION_DISABLED"]:
        return
    user_id = session.get("user_id")
    authenticated_at = session.get("authenticated_at")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return
    if not isinstance(authenticated_at, (int, float)):
        session.clear()
        return
    session_age = time.time() - authenticated_at
    if session_age > current_app.permanent_session_lifetime.total_seconds():
        session.clear()
        g.session_expired = True
        return
    user = db.session.get(User, user_id)
    if user is None or not user.active:
        session.clear()
        return
    g.current_user = user
    session.permanent = True


def _authorize_request() -> Response | None:
    if current_app.config["AUTHENTICATION_DISABLED"]:
        return None
    endpoint = request.endpoint
    if endpoint in _PUBLIC_ENDPOINTS or endpoint is None:
        return None
    user: User | None = g.current_user
    if user is None:
        wants_json = request.accept_mimetypes.best == "application/json"
        if wants_json or request.path.startswith("/api/"):
            abort(401)
        login_args = {"next": request.full_path.rstrip("?")}
        if g.get("session_expired"):
            login_args["reason"] = "session_expired"
        return redirect(url_for("auth.login", **login_args))
    if user.role == UserRole.COACH:
        return None
    if user.role != UserRole.ATHLETE or endpoint not in _ATHLETE_ENDPOINTS:
        abort(403)
    athlete_id = _requested_athlete_id()
    if athlete_id is not None and athlete_id != user.athlete_id:
        abort(404)
    return None


def _enforce_csrf() -> None:
    if current_app.config["AUTHENTICATION_DISABLED"] or request.method in _SAFE_METHODS:
        return
    if request.endpoint == "auth.login" and "csrf_token" not in session:
        # The initial token is created while rendering the login form. Requests
        # without that session-bound token are always rejected.
        abort(400, description="Invalid CSRF token.")
    _validate_csrf()


def init_auth(app) -> None:
    app.register_blueprint(auth_bp)
    app.before_request(_load_identity)
    app.before_request(_authorize_request)
    app.before_request(_enforce_csrf)
    app.jinja_env.globals["csrf_token"] = _csrf_token
    def athlete_context() -> dict[str, object]:
        athlete_id = (
            g.current_user.athlete_id
            if g.get("current_user") is not None
            else session.get("athlete_id")
        )
        services = (
            athlete_services(athlete_id)
            if isinstance(athlete_id, int) and not isinstance(athlete_id, bool)
            else None
        )
        return {
            "current_user": g.get("current_user"),
            "athlete_navigation_id": athlete_id,
            "athlete_services": services,
        }

    app.context_processor(athlete_context)
    app.after_request(_inject_csrf_fields)

    @app.cli.command("create-user")
    @click.argument("email")
    @click.option(
        "--role", type=click.Choice([role.value for role in UserRole]), required=True
    )
    @click.option("--athlete-id", type=int)
    @click.password_option(confirmation_prompt=True)
    def create_user(
        email: str, role: str, athlete_id: int | None, password: str
    ) -> None:
        """Create a coach or athlete login without accepting plaintext via argv."""
        normalized_email = email.strip().casefold()
        if User.query.filter_by(email=normalized_email).first() is not None:
            raise click.ClickException("A user with that email already exists.")
        if (role == UserRole.ATHLETE) != (athlete_id is not None):
            raise click.ClickException(
                "Athlete users require --athlete-id; coaches do not."
            )
        if athlete_id is not None and db.session.get(Athlete, athlete_id) is None:
            raise click.ClickException("Athlete does not exist.")
        user = User(email=normalized_email, role=role, athlete_id=athlete_id)
        try:
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Created {role} user {normalized_email}.")

    @app.cli.command("account-delivery-readiness")
    def account_delivery_readiness() -> None:
        """Print redacted invitation delivery configuration."""
        from .services.transactional_email import delivery_readiness

        readiness = delivery_readiness()
        for key in ("public_base_url", "transport", "tls", "smtp_auth"):
            click.echo(f"{key}: {readiness[key]}")


def _inject_csrf_fields(response: Response) -> Response:
    """Add CSRF fields to existing server-rendered forms during migration."""
    if (
        current_app.config["AUTHENTICATION_DISABLED"]
        or not response.content_type.startswith("text/html")
        or response.direct_passthrough
    ):
        return response
    html = response.get_data(as_text=True)
    if "<form" not in html:
        return response
    field = '<input type="hidden" name="csrf_token" value="' + _csrf_token() + '">'
    html = re.sub(r"(<form\b[^>]*>)", rf"\1{field}", html, flags=re.IGNORECASE)
    response.set_data(html)
    return response


def roles_required(*roles: UserRole):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get("current_user")
            if user is None:
                abort(401)
            if user.user_role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("current_user") is not None:
        return redirect(_default_destination(g.current_user))
    error = None
    session_expired = request.args.get("reason") == "session_expired"
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()
        password = request.form.get("password", "")
        key = _client_key(email)
        user = User.query.filter_by(email=email, active=True).first()
        limited = _is_rate_limited(key)
        password_valid = check_password_hash(
            user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
            password,
        )
        valid = not limited and user is not None and password_valid
        if valid:
            _attempts.pop(key, None)
            session.clear()
            session["user_id"] = user.id
            session["authenticated_at"] = time.time()
            session["athlete_id"] = user.athlete_id
            session.permanent = True
            target = request.form.get("next")
            # The legacy overview at `/` is not a useful post-authentication
            # destination. Some external entry points still submit it as their
            # generic default, so let role-aware routing handle that case.
            if target != "/" and _safe_redirect_target(target):
                return redirect(target)
            return redirect(_default_destination(user))
        if not limited:
            _record_failure(key)
        error = "Invalid email or password."
        status = 429 if limited else 401
        response = Response(
            render_template(
                "auth/login.html",
                error=error,
                next=request.values.get("next", ""),
                email=_edge_email(),
                edge_email=_edge_email(),
                session_expired=session_expired,
            ),
            status=status,
            content_type="text/html; charset=utf-8",
        )
        if limited:
            response.headers["Retry-After"] = str(
                current_app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"]
            )
        return response
    return render_template(
        "auth/login.html",
        error=error,
        next=request.values.get("next", ""),
        email=_edge_email(),
        edge_email=_edge_email(),
        session_expired=session_expired,
    )


@auth_bp.route("/account/<purpose>", methods=["GET", "POST"])
def account_token(purpose: str):
    from .models.account_token import AccountTokenPurpose
    from .services.account_lifecycle import (
        AccountLifecycleError,
        consume_token,
        token_record,
    )

    try:
        token_purpose = AccountTokenPurpose(purpose)
    except ValueError:
        abort(404)
    token = request.form.get("account_token", "") if request.method == "POST" else ""
    record = token_record(token, token_purpose) if token else None
    available = request.method == "GET" or (record is not None and record.is_available)
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if password != confirmation:
            error = "The passwords do not match."
        else:
            try:
                user = consume_token(token, token_purpose, password)
            except (AccountLifecycleError, ValueError) as exc:
                error = str(exc)
            else:
                session.clear()
                session["user_id"] = user.id
                session["authenticated_at"] = time.time()
                session["athlete_id"] = user.athlete_id
                session.permanent = True
                welcome = (
                    "activated"
                    if token_purpose == AccountTokenPurpose.INVITATION
                    else "password-updated"
                )
                return redirect(url_for("athletes.dashboard", welcome=welcome))
        record = token_record(token, token_purpose)
        available = record is not None and record.is_available
    response = Response(
        render_template(
            "auth/set_password.html",
            purpose=token_purpose,
            available=available,
            error=error,
            account_token=token if available else "",
        ),
        status=(410 if error and not available else 400) if error else (200 if available else 410),
        content_type="text/html; charset=utf-8",
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
