import secrets
import string
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import audit, password_hash, require_permission
from app.db.session import get_db
from app.models.entities import Role, User, UserSession
from app.schemas.auth import CreateUserRequest, UpdateUserRequest, UserList, UserView
from app.api.auth import user_view

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(20))


def lock_admin_transition(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(729184203)"))


@router.get("", response_model=UserList)
def list_users(request: Request, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = Query(None, max_length=100), db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    query = select(User)
    count_query = select(func.count()).select_from(User)
    if search:
        value = f"%{search.strip().lower()}%"
        condition = or_(User.username.ilike(value), User.email.ilike(value))
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = db.scalar(count_query) or 0
    users = db.scalars(query.order_by(User.username).offset((page - 1) * page_size).limit(page_size)).all()
    return UserList(items=[user_view(db, item) for item in users], page=page, page_size=page_size, total=total)


@router.post("", status_code=201)
def create_user(payload: CreateUserRequest, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise HTTPException(status_code=400, detail="invalid role")
    temp = temporary_password()
    user = User(username=payload.username, email=payload.email, password_hash=password_hash.hash(temp), role_id=role.id, must_change_password=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="user already exists") from None
    audit(db, actor, "user_created", "user", "success", entity_id=str(user.id))
    db.commit()
    return {"user": user_view(db, user), "temporary_password": temp}


@router.get("/{user_id}", response_model=UserView)
def get_user(user_id: UUID, actor: User = Depends(require_permission("user.manage")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user_view(db, user)


@router.patch("/{user_id}", response_model=UserView)
def update_user(user_id: UUID, payload: UpdateUserRequest, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    if payload.role is not None:
        lock_admin_transition(db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        role = db.scalar(select(Role).where(Role.name == payload.role))
        if role is None:
            raise HTTPException(status_code=400, detail="invalid role")
        old_role = db.get(Role, user.role_id)
        if old_role and old_role.name == "administrator" and role.name != "administrator" and user.is_active:
            admins = db.scalars(select(User).join(Role, Role.id == User.role_id).where(Role.name == "administrator", User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
            if len(admins) <= 1:
                raise HTTPException(status_code=400, detail="cannot remove last administrator")
        previous_role = old_role.name if old_role else None
        user.role_id = role.id
    else:
        previous_role = None
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="user already exists") from None
    if payload.role is not None and previous_role != role.name:
        audit(db, actor, "role_changed", "user", "success", entity_id=str(user.id), metadata={"previous_role": previous_role, "new_role": role.name})
    audit(db, actor, "user_updated", "user", "success", entity_id=str(user.id))
    db.commit()
    return user_view(db, user)


def set_active(user_id: UUID, active: bool, request: Request, db: Session, actor: User) -> UserView:
    lock_admin_transition(db)
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not active and user.id == actor.id:
        raise HTTPException(status_code=400, detail="cannot deactivate current user")
    if not active and user.is_active and user.role_id:
        role = db.get(Role, user.role_id)
        if role and role.name == "administrator":
            admins = db.scalars(select(User).join(Role, Role.id == User.role_id).where(Role.name == "administrator", User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
            if len(admins) <= 1:
                raise HTTPException(status_code=400, detail="cannot deactivate last administrator")
    user.is_active = active
    if not active:
        db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).update({UserSession.revoked_at: func.now()}, synchronize_session=False)
    audit(db, actor, "user_activated" if active else "user_deactivated", "user", "success", entity_id=str(user.id))
    db.commit()
    return user_view(db, user)


@router.post("/{user_id}/activate", response_model=UserView)
def activate(user_id: UUID, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    return set_active(user_id, True, request, db, actor)


@router.post("/{user_id}/deactivate", response_model=UserView)
def deactivate(user_id: UUID, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    return set_active(user_id, False, request, db, actor)


@router.post("/{user_id}/reset-password")
def reset_password(user_id: UUID, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_permission("user.manage"))):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    temp = temporary_password()
    user.password_hash = password_hash.hash(temp)
    user.must_change_password = True
    db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).update({UserSession.revoked_at: func.now()}, synchronize_session=False)
    audit(db, actor, "password_reset", "user", "success", entity_id=str(user.id))
    db.commit()
    return {"temporary_password": temp}
