import getpass
import re

from sqlalchemy import select

from app.core.security import audit, password_hash
from app.db.session import SessionLocal
from app.models.entities import Role, User

USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")


def prompt_admin() -> tuple[str, str, str]:
    username = input("Username: ").strip().lower()
    email = input("Email: ").strip().lower()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not USERNAME.fullmatch(username):
        raise ValueError("username must use lowercase letters, numbers, '.', '_' or '-'")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 320:
        raise ValueError("invalid email")
    if not 12 <= len(password) <= 128:
        raise ValueError("password must contain 12 to 128 characters")
    if password != confirmation:
        raise ValueError("passwords do not match")
    return username, email, password


def create_admin() -> None:
    username, email, password = prompt_admin()
    with SessionLocal.begin() as db:
        if db.scalar(select(User).where((User.username == username) | (User.email == email))):
            raise ValueError("user already exists")
        role = db.scalar(select(Role).where(Role.name == "administrator"))
        if role is None:
            raise RuntimeError("administrator role is not seeded")
        if db.scalar(select(User).join(Role, Role.id == User.role_id).where(Role.name == "administrator")):
            raise ValueError("administrator already exists; use the admin API")
        user = User(username=username, email=email, password_hash=password_hash.hash(password), role_id=role.id, must_change_password=False)
        db.add(user)
        db.flush()
        audit(db, user, "admin_created", "user", "success", entity_id=str(user.id))
    print(f"Administrator created: {username}")


if __name__ == "__main__":
    try:
        create_admin()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
