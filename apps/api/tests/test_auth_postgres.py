import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.entities import Permission, Role, RolePermission, User
from app.core.security import password_hash

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")


@pytest.fixture
def auth_client():
    database_name = make_url(TEST_DATABASE_URL).database
    assert database_name == "orvexadb_test" or database_name.startswith("orvexadb_test_")
    schema = f"auth_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    scoped_engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-c search_path={schema}"})
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        public_before = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
    try:
        with scoped_engine.connect() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        local_session = sessionmaker(bind=scoped_engine, autoflush=False, expire_on_commit=False)
        with local_session.begin() as db:
            admin_role = Role(name="administrator")
            employee_role = Role(name="employee")
            permission = Permission(code="user.manage")
            db.add_all([admin_role, employee_role, permission])
            db.flush()
            db.add(RolePermission(role_id=admin_role.id, permission_id=permission.id))
            db.add(User(username="admin", email="admin@example.com", password_hash=password_hash.hash("correct horse battery"), role_id=admin_role.id, must_change_password=False))
        def override_db():
            with local_session() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        with TestClient(app, base_url="http://localhost:3000") as client:
            client._db_factory = local_session
            yield client
    finally:
        app.dependency_overrides.clear()
        with admin_engine.begin() as connection:
            public_after = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
            assert public_after == public_before
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        scoped_engine.dispose()
        admin_engine.dispose()


def origin_headers(csrf: str | None = None) -> dict[str, str]:
    headers = {"Origin": "http://localhost:3000"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return headers


def test_login_origin_generic_error_and_session(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "wrong"}, headers=origin_headers())
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"
    response = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    assert response.status_code == 200
    assert "orvexadb_session" in response.cookies
    assert "orvexadb_csrf" in response.cookies
    missing = auth_client.post("/api/v1/auth/login", json={"identifier": "missing", "password": "wrong"}, headers=origin_headers())
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Usuario o contraseña incorrectos"
    with auth_client._db_factory() as db:
        from app.models.entities import AuditLog
        failed = db.query(AuditLog).filter_by(action="login_failed").all()
        assert failed
        assert all(item.metadata_json is None for item in failed)


def test_logout_requires_csrf_and_revoked_session_rejects_me(auth_client: TestClient) -> None:
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    assert auth_client.post("/api/v1/auth/logout", headers=origin_headers()).status_code == 403
    csrf = login.cookies["orvexadb_csrf"]
    assert auth_client.post("/api/v1/auth/logout", headers=origin_headers(csrf)).status_code == 204
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_activity_renews_idle_expiry_and_requires_csrf_origin(auth_client: TestClient) -> None:
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    csrf = login.cookies["orvexadb_csrf"]
    with auth_client._db_factory() as db:
        from app.models.entities import UserSession
        session = db.query(UserSession).one()
        before = session.expires_at
        session.expires_at = datetime.now(UTC) + timedelta(minutes=1)
        db.commit()
    assert auth_client.post("/api/v1/auth/activity", headers=origin_headers()).status_code == 403
    assert auth_client.post("/api/v1/auth/activity", headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf}).status_code == 403
    assert auth_client.post("/api/v1/auth/activity", headers=origin_headers(csrf)).status_code == 204
    with auth_client._db_factory() as db:
        session = db.query(UserSession).one()
        assert session.expires_at > before


def test_expired_me_persists_revocation_and_logout_clears_cookies(auth_client: TestClient) -> None:
    auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    with auth_client._db_factory() as db:
        from app.models.entities import UserSession
        session = db.query(UserSession).one()
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    with auth_client._db_factory() as db:
        session = db.query(UserSession).one()
        assert session.revoked_at is not None
    logout = auth_client.post("/api/v1/auth/logout", headers=origin_headers())
    assert logout.status_code == 204
    deleted = logout.headers.get_list("set-cookie")
    assert any(value.startswith("orvexadb_session=") and "Max-Age=0" in value for value in deleted)
    assert any(value.startswith("orvexadb_csrf=") and "Max-Age=0" in value for value in deleted)
    assert "orvexadb_session" not in auth_client.cookies
    assert "orvexadb_csrf" not in auth_client.cookies


def test_expired_session_and_inactive_user_are_rejected(auth_client: TestClient) -> None:
    _login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    with auth_client._db_factory() as db:
        from app.models.entities import User, UserSession
        session = db.query(UserSession).one()
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    with auth_client._db_factory() as db:
        user = db.query(User).filter_by(username="admin").one()
        user.is_active = False
        db.commit()
    assert auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers()).status_code == 401


def test_csrf_and_origin_are_required_for_password_change(auth_client: TestClient) -> None:
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    csrf = login.cookies["orvexadb_csrf"]
    payload = {"current_password": "correct horse battery", "new_password": "new secure passphrase"}
    assert auth_client.post("/api/v1/auth/change-password", json=payload, headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf}).status_code == 403
    assert auth_client.post("/api/v1/auth/change-password", json=payload, headers=origin_headers("wrong-csrf")).status_code == 403
    assert auth_client.post("/api/v1/auth/change-password", json=payload, headers={"Origin": "http://localhost:3000"}).status_code == 403
    assert auth_client.post("/api/v1/auth/change-password", json=payload, headers=origin_headers(csrf)).status_code == 200
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_login_is_rate_limited_after_five_failures(auth_client: TestClient) -> None:
    for _ in range(4):
        response = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "wrong"}, headers=origin_headers())
        assert response.status_code == 401
    response = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "wrong"}, headers=origin_headers())
    assert response.status_code == 429
    with auth_client._db_factory() as db:
        from app.models.entities import LoginAttempt
        attempt = db.query(LoginAttempt).one()
        assert attempt.failure_count == 5
        assert attempt.blocked_until is not None
        assert attempt.blocked_until > datetime.now(UTC) + timedelta(minutes=14)
        assert attempt.blocked_until < datetime.now(UTC) + timedelta(minutes=16)
    response = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "wrong"}, headers=origin_headers())
    assert response.status_code == 429


def test_admin_create_and_self_deactivation_protection(auth_client: TestClient) -> None:
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    csrf = login.cookies["orvexadb_csrf"]
    headers = origin_headers(csrf)
    created = auth_client.post("/api/v1/admin/users", json={"username": "employee", "email": "employee@example.com", "role": "employee"}, headers=headers)
    assert created.status_code == 201
    assert "password_hash" not in created.text
    assert "temporary_password" in created.json()
    admin_id = login.json()["id"]
    response = auth_client.post(f"/api/v1/admin/users/{admin_id}/deactivate", headers=headers)
    assert response.status_code == 400


def test_role_change_has_explicit_audit_event(auth_client: TestClient) -> None:
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    csrf = login.cookies["orvexadb_csrf"]
    created = auth_client.post("/api/v1/admin/users", json={"username": "employee", "email": "employee@example.com", "role": "employee"}, headers=origin_headers(csrf))
    user_id = created.json()["user"]["id"]
    changed = auth_client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "administrator"}, headers=origin_headers(csrf))
    assert changed.status_code == 200
    with auth_client._db_factory() as db:
        from app.models.entities import AuditLog
        event = db.query(AuditLog).filter_by(action="role_changed", entity_id=user_id).one()
        assert event.metadata_json == {"previous_role": "employee", "new_role": "administrator"}


def test_admin_lifecycle_search_pagination_and_reset_revokes_sessions(auth_client: TestClient) -> None:
    admin_login = auth_client.post("/api/v1/auth/login", json={"identifier": "admin", "password": "correct horse battery"}, headers=origin_headers())
    csrf = admin_login.cookies["orvexadb_csrf"]
    headers = origin_headers(csrf)
    created = auth_client.post("/api/v1/admin/users", json={"username": "lifecycle", "email": "lifecycle@example.com", "role": "employee"}, headers=headers)
    assert created.status_code == 201
    employee_id = created.json()["user"]["id"]
    temporary = created.json()["temporary_password"]
    listing = auth_client.get("/api/v1/admin/users?page=1&page_size=1&search=lifecycle")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["username"] == "lifecycle"
    assert "password_hash" not in listing.text
    updated = auth_client.patch(f"/api/v1/admin/users/{employee_id}", json={"email": "life@example.com"}, headers=headers)
    assert updated.status_code == 200
    assert auth_client.post(f"/api/v1/admin/users/{employee_id}/deactivate", headers=headers).status_code == 200
    assert auth_client.post(f"/api/v1/admin/users/{employee_id}/activate", headers=headers).status_code == 200
    employee_login = auth_client.post("/api/v1/auth/login", json={"identifier": "lifecycle", "password": temporary}, headers=origin_headers())
    assert employee_login.status_code == 200
    auth_client.cookies.update(admin_login.cookies)
    reset = auth_client.post(f"/api/v1/admin/users/{employee_id}/reset-password", headers=headers)
    assert reset.status_code == 200
    with auth_client._db_factory() as db:
        from app.models.entities import AuditLog, UserSession
        sessions = db.query(UserSession).filter_by(user_id=employee_id).all()
        assert sessions and all(session.revoked_at is not None for session in sessions)
        events = db.query(AuditLog).filter(AuditLog.entity_id == employee_id).all()
        assert {event.action for event in events} >= {"user_created", "user_updated", "user_deactivated", "user_activated", "password_reset"}
        assert all(event.metadata_json is None or "password" not in str(event.metadata_json).lower() for event in events)


def test_permission_is_loaded_from_database_and_employee_is_forbidden(auth_client: TestClient) -> None:
    with auth_client._db_factory() as db:
        from app.models.entities import Role, User
        employee_role = db.query(Role).filter_by(name="employee").one()
        db.add(User(username="employee", email="employee@example.com", password_hash=password_hash.hash("employee secure pass"), role_id=employee_role.id, must_change_password=False))
        db.commit()
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "employee", "password": "employee secure pass"}, headers=origin_headers())
    assert login.status_code == 200
    assert auth_client.get("/api/v1/admin/users").status_code == 403


def test_must_change_password_restricts_other_permissions(auth_client: TestClient) -> None:
    with auth_client._db_factory() as db:
        from app.models.entities import Role, User
        employee_role = db.query(Role).filter_by(name="employee").one()
        db.add(User(username="temporary", email="temporary@example.com", password_hash=password_hash.hash("temporary secure pass"), role_id=employee_role.id, must_change_password=True))
        db.commit()
    login = auth_client.post("/api/v1/auth/login", json={"identifier": "temporary", "password": "temporary secure pass"}, headers=origin_headers())
    assert login.status_code == 200
    assert auth_client.get("/api/v1/admin/users").status_code == 403
