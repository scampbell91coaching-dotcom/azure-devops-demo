from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from ..extensions import db
from ..models.account_token import AccountToken, AccountTokenPurpose, DeliveryState
from ..models.athlete import Athlete
from ..models.user import User, UserRole
from .transactional_email import send_account_invitation, send_password_reset


class AccountLifecycleError(ValueError):
    pass


@dataclass(frozen=True)
class IssuedAccountToken:
    record: AccountToken
    raw_token: str


def digest_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def account_state(athlete: Athlete) -> str:
    if athlete.user is not None and athlete.user.active:
        return "active"
    invitation = latest_token(athlete.id, AccountTokenPurpose.INVITATION)
    return "invited" if invitation is not None and invitation.is_available else "not_invited"


def latest_token(athlete_id: int, purpose: AccountTokenPurpose) -> AccountToken | None:
    return (
        AccountToken.query.filter_by(athlete_id=athlete_id, purpose=purpose.value)
        .order_by(AccountToken.created_at.desc(), AccountToken.id.desc())
        .first()
    )


def _user_for_invitation(athlete: Athlete) -> User:
    linked = athlete.user
    email_owner = User.query.filter(db.func.lower(User.email) == athlete.email.casefold()).first()
    if email_owner is not None and email_owner.athlete_id != athlete.id:
        raise AccountLifecycleError("That email already belongs to another account.")
    if linked is not None:
        if linked.email.casefold() != athlete.email.casefold():
            raise AccountLifecycleError("The athlete email does not match the linked account.")
        if linked.active:
            raise AccountLifecycleError("This athlete account is already active.")
        return linked
    user = User(
        email=athlete.email.casefold(),
        role=UserRole.ATHLETE,
        athlete_id=athlete.id,
        active=False,
        password_hash=None,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _issue(athlete: Athlete, user: User, purpose: AccountTokenPurpose, lifetime: timedelta) -> IssuedAccountToken:
    if lifetime <= timedelta(0):
        raise AccountLifecycleError("The account link lifetime must be positive.")
    now = datetime.now(UTC)
    AccountToken.query.filter_by(
        athlete_id=athlete.id, purpose=purpose.value, consumed_at=None, revoked_at=None
    ).update({"revoked_at": now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    record = AccountToken(
        purpose=purpose.value,
        token_digest=digest_token(raw_token),
        athlete_id=athlete.id,
        user_id=user.id,
        expires_at=now + lifetime,
        delivery_state=DeliveryState.PENDING,
    )
    db.session.add(record)
    db.session.commit()
    return IssuedAccountToken(record, raw_token)


def create_invitation(athlete: Athlete, *, activation_url: str, lifetime: timedelta) -> IssuedAccountToken:
    issued = _issue(athlete, _user_for_invitation(athlete), AccountTokenPurpose.INVITATION, lifetime)
    result = send_account_invitation(
        recipient=athlete.email,
        athlete_name=athlete.first_name,
        activation_url=activation_url.format(token=issued.raw_token),
    )
    _record_delivery(issued.record, result.state, result.detail)
    return issued


def create_password_reset(athlete: Athlete, *, reset_url: str, lifetime: timedelta) -> IssuedAccountToken:
    user = athlete.user
    if user is None or not user.active or not user.password_hash:
        raise AccountLifecycleError("The athlete account must be active before resetting its password.")
    if user.email.casefold() != athlete.email.casefold():
        raise AccountLifecycleError("The athlete email does not match the linked account.")
    issued = _issue(athlete, user, AccountTokenPurpose.PASSWORD_RESET, lifetime)
    result = send_password_reset(
        recipient=athlete.email,
        athlete_name=athlete.first_name,
        reset_url=reset_url.format(token=issued.raw_token),
    )
    _record_delivery(issued.record, result.state, result.detail)
    return issued


def _record_delivery(record: AccountToken, state: str, detail: str | None) -> None:
    record.delivery_state = state
    record.delivery_detail = detail
    record.delivered_at = datetime.now(UTC) if state == DeliveryState.SENT else None
    db.session.commit()


def revoke_tokens(athlete_id: int, purpose: AccountTokenPurpose) -> int:
    result = AccountToken.query.filter_by(
        athlete_id=athlete_id, purpose=purpose.value, consumed_at=None, revoked_at=None
    ).update({"revoked_at": datetime.now(UTC)}, synchronize_session=False)
    db.session.commit()
    return result


def token_record(raw_token: str, purpose: AccountTokenPurpose) -> AccountToken | None:
    if not raw_token or len(raw_token) > 200:
        return None
    return AccountToken.query.filter_by(
        token_digest=digest_token(raw_token), purpose=purpose.value
    ).first()


def consume_token(raw_token: str, purpose: AccountTokenPurpose, password: str) -> User:
    record = token_record(raw_token, purpose)
    if record is None or not record.is_available:
        raise AccountLifecycleError("This link is invalid, expired, revoked, or already used.")
    user = db.session.get(User, record.user_id)
    if user is None or user.athlete_id != record.athlete_id or user.role != UserRole.ATHLETE:
        raise AccountLifecycleError("This link cannot be matched to an athlete account.")
    user.set_password(password)
    if purpose == AccountTokenPurpose.INVITATION:
        if user.active:
            raise AccountLifecycleError("This invitation has already been used.")
        user.active = True
    now = datetime.now(UTC)
    result = db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.id == record.id,
            AccountToken.consumed_at.is_(None),
            AccountToken.revoked_at.is_(None),
            AccountToken.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.session.rollback()
        raise AccountLifecycleError("This link is invalid, expired, revoked, or already used.")
    db.session.commit()
    return user
