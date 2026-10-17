import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AuditLog, LoginAttempt, Permission, RolePermission, User, UserSession

SESSION_COOKIE = "orvexadb_session"
CSRF_COOKIE = "orvexadb_csrf"
SESSION_IDLE_MINUTES = 5
password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$9OjMt/mWP8GClDKp6lH8ww$5kyK5UbQupzszw/jNXat1JDSiVlbAQMy/kRsvjEQY90"


def normalize_identifier(value: str) -> str:
    return value.strip().casefold()


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def attempt_key(identifier: str, host: str) -> str:
    raw = f"{normalize_identifier(identifier)}\x00{host}".encode()
    return hmac.new(get_settings().auth_pepper.encode(), raw, hashlib.sha256).hexdigest()


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") not in get_settings().origin_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="origin not allowed")


def audit(db: Session, actor: User | None, action: str, entity: str, result: str, entity_id: str | None = None, metadata: dict | None = None) -> None:
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity=entity, entity_id=entity_id, result=result, metadata_json=metadata))


def _now() -> datetime:
    return datetime.now(UTC)


def check_login_limit(db: Session, identifier: str, host: str) -> tuple[str, bool]:
    key = attempt_key(identifier, host)
    db.execute(insert(LoginAttempt).values(key_hmac=key).on_conflict_do_nothing(index_elements=[LoginAttempt.key_hmac]))
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.key_hmac == key).with_for_update())
    now = _now()
    if row is None:
        row = LoginAttempt(key_hmac=key, window_started_at=now, failure_count=0)
        db.add(row)
        db.flush()
    if row.blocked_until and row.blocked_until > now:
        return key, True
    if row.window_started_at + timedelta(minutes=15) <= now:
        row.window_started_at = now
        row.failure_count = 0
        row.blocked_until = None
    return key, False


def record_login_failure(db: Session, key: str) -> bool:
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.key_hmac == key).with_for_update())
    if row is None:
        return False
    row.failure_count += 1
    if row.failure_count >= 5:
        row.blocked_until = _now() + timedelta(minutes=15)
        return True
    return False


def clear_login_failures(db: Session, key: str) -> None:
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.key_hmac == key).with_for_update())
    if row:
        row.failure_count = 0
        row.blocked_until = None
        row.window_started_at = _now()


def create_session(db: Session, user: User) -> tuple[str, str, UserSession]:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(48)
    session = UserSession(user_id=user.id, token_hash=hash_token(token), csrf_token_hash=hash_token(csrf), expires_at=_now() + timedelta(minutes=SESSION_IDLE_MINUTES))
    db.add(session)
    db.flush()
    return token, csrf, session


def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    secure = get_settings().auth_cookie_secure
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=secure, samesite="lax", path="/", max_age=get_settings().auth_session_hours * 3600)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="lax", path="/", max_age=get_settings().auth_session_hours * 3600)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def current_session(request: Request, db: Session) -> tuple[User, UserSession]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)).with_for_update())
    if not session or session.revoked_at:
        raise HTTPException(status_code=401, detail="authentication required")
    if session.expires_at <= _now():
        session.revoked_at = _now()
        db.commit()
        raise HTTPException(status_code=401, detail="authentication required")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="authentication required")
    return user, session


def refresh_session_activity(session: UserSession) -> None:
    now = _now()
    absolute_deadline = session.created_at + timedelta(hours=get_settings().auth_session_hours) if session.created_at else now + timedelta(hours=get_settings().auth_session_hours)
    session.expires_at = min(now + timedelta(minutes=SESSION_IDLE_MINUTES), absolute_deadline)


def require_csrf(request: Request, session: UserSession) -> None:
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or not hmac.compare_digest(header, cookie) or not hmac.compare_digest(hash_token(header), session.csrf_token_hash):
        raise HTTPException(status_code=403, detail="csrf validation failed")
    validate_origin(request)


def require_permission(code: str):
    def dependency(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
        user, session = current_session(request, db)
        if user.must_change_password and request.url.path not in {"/api/v1/auth/me", "/api/v1/auth/change-password", "/api/v1/auth/logout"}:
            raise HTTPException(status_code=403, detail="password change required")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            require_csrf(request, session)
        allowed = db.scalar(select(Permission.id).join(RolePermission, RolePermission.permission_id == Permission.id).where(RolePermission.role_id == user.role_id, Permission.code == code))
        if allowed is None:
            raise HTTPException(status_code=403, detail="permission denied")
        request.state.current_user = user
        return user
    return dependency
