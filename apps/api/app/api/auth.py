from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    audit,
    check_login_limit,
    clear_auth_cookies,
    clear_login_failures,
    create_session,
    current_session,
    normalize_identifier,
    password_hash,
    record_login_failure,
    require_csrf,
    refresh_session_activity,
    set_auth_cookies,
    validate_origin,
)
from app.db.session import get_db
from app.models.entities import Permission, Role, RolePermission, User, UserSession
from app.schemas.auth import ChangePasswordRequest, LoginRequest, UserView

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(db: Session, user: User) -> UserView:
    role = db.get(Role, user.role_id) if user.role_id else None
    permissions = list(db.scalars(select(Permission.code).join(RolePermission, RolePermission.permission_id == Permission.id).where(RolePermission.role_id == user.role_id))) if user.role_id else []
    return UserView(id=user.id, username=user.username, email=user.email, is_active=user.is_active, must_change_password=user.must_change_password, role=role.name if role else None, permissions=permissions, last_login_at=user.last_login_at)


@router.post("/login", response_model=UserView)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    validate_origin(request)
    identifier = normalize_identifier(payload.identifier)
    host = request.client.host if request.client else "unknown"
    key, blocked = check_login_limit(db, identifier, host)
    if blocked:
        db.commit()
        raise HTTPException(status_code=429, detail="too many login attempts")
    user = db.scalar(select(User).where((User.username == identifier) | (User.email == identifier)).with_for_update())
    valid = password_hash.verify(payload.password, user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH)
    if not user or not valid or not user.is_active:
        locked = record_login_failure(db, key)
        audit(db, None, "login_failed", "user", "blocked" if locked else "failure")
        db.commit()
        if locked:
            raise HTTPException(status_code=429, detail="too many login attempts")
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    clear_login_failures(db, key)
    user.last_login_at = datetime.now(UTC)
    token, csrf, _session = create_session(db, user)
    audit(db, user, "login", "user", "success", entity_id=str(user.id))
    db.commit()
    set_auth_cookies(response, token, csrf)
    return user_view(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    validate_origin(request)
    try:
        user, session = current_session(request, db)
    except HTTPException as error:
        if error.status_code == 401:
            clear_auth_cookies(response)
            return
        raise
    require_csrf(request, session)
    session.revoked_at = datetime.now(UTC)
    audit(db, user, "logout", "user", "success", entity_id=str(user.id))
    db.commit()
    clear_auth_cookies(response)


@router.get("/me", response_model=UserView)
def me(request: Request, db: Session = Depends(get_db)):
    user, _session = current_session(request, db)
    return user_view(db, user)


@router.post("/activity", status_code=204)
def activity(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        _user, session = current_session(request, db)
    except HTTPException as error:
        if error.status_code == 401:
            clear_auth_cookies(response)
        raise
    require_csrf(request, session)
    refresh_session_activity(session)
    db.commit()


@router.post("/change-password", response_model=UserView)
def change_password(payload: ChangePasswordRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user, session = current_session(request, db)
    require_csrf(request, session)
    if not password_hash.verify(payload.current_password, user.password_hash or DUMMY_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="current password invalid")
    user.password_hash = password_hash.hash(payload.new_password)
    user.must_change_password = False
    db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).update({UserSession.revoked_at: datetime.now(UTC)}, synchronize_session=False)
    audit(db, user, "password_changed", "user", "success", entity_id=str(user.id))
    db.commit()
    clear_auth_cookies(response)
    return user_view(db, user)
