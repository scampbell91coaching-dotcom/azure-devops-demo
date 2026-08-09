from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

from flask import current_app

CANONICAL_SENDER_NAME = "Traditional Strength"
CANONICAL_SENDER_ADDRESS = "coach@traditionalstrength.co.uk"


@dataclass(frozen=True)
class EmailDeliveryResult:
    state: str
    detail: str | None = None


class EmailTransport(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SMTPTransport:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(message)


class MemoryEmailTransport:
    """Explicit development/test transport; messages never leave the process."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


def configured_transport() -> EmailTransport | None:
    injected = current_app.config.get("EMAIL_TRANSPORT")
    if injected is not None:
        return injected
    host = current_app.config.get("SMTP_HOST")
    if not host:
        return None
    return SMTPTransport(
        str(host),
        int(current_app.config["SMTP_PORT"]),
        current_app.config.get("SMTP_USERNAME"),
        current_app.config.get("SMTP_PASSWORD"),
        bool(current_app.config["SMTP_USE_TLS"]),
    )


def _send(*, recipient: str, subject: str, text: str) -> EmailDeliveryResult:
    transport = configured_transport()
    if transport is None:
        return EmailDeliveryResult("not_configured", "No transactional email provider is configured.")
    message = EmailMessage()
    message["From"] = formataddr((CANONICAL_SENDER_NAME, CANONICAL_SENDER_ADDRESS))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text)
    try:
        transport.send(message)
    except Exception:  # noqa: BLE001 - provider failures become explicit domain state.
        # Provider exceptions can include request content; never put token-bearing
        # email bodies or URLs into application logs.
        current_app.logger.warning("Transactional email delivery failed")
        return EmailDeliveryResult("failed", "The email provider rejected or failed the delivery request.")
    return EmailDeliveryResult("sent")


def send_account_invitation(*, recipient: str, athlete_name: str, activation_url: str) -> EmailDeliveryResult:
    return _send(
        recipient=recipient,
        subject="Activate your Traditional Strength account",
        text=(
            f"Hello {athlete_name},\n\n"
            "Your Traditional Strength athlete account is ready. Set your password using "
            f"this one-time link:\n\n{activation_url}\n\n"
            "If you were not expecting this invitation, you can ignore this email."
        ),
    )


def send_password_reset(*, recipient: str, athlete_name: str, reset_url: str) -> EmailDeliveryResult:
    return _send(
        recipient=recipient,
        subject="Reset your Traditional Strength password",
        text=(
            f"Hello {athlete_name},\n\n"
            "A password reset was created for your account. Choose a new password using "
            f"this one-time link:\n\n{reset_url}\n\n"
            "If you were not expecting this reset, contact your coach."
        ),
    )
