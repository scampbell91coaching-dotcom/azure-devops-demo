from __future__ import annotations

from flask import Flask, Response

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
    "media-src 'self'; object-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net; style-src 'self'; "
    "upgrade-insecure-requests"
)


def init_security_headers(app: Flask, *, prevent_caching: bool = False) -> None:
    """Apply browser security headers at the application boundary."""

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        # WebKit does not implement upgrade-insecure-requests consistently in
        # Flask's in-process HTTP test environment. Production keeps the
        # directive; only explicitly testing applications omit it.
        if app.testing:
            response.headers["Content-Security-Policy"] = (
                CONTENT_SECURITY_POLICY.replace("; upgrade-insecure-requests", "")
            )
        else:
            response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=()"
        )
        if prevent_caching:
            response.headers["Cache-Control"] = "no-store"
        return response
