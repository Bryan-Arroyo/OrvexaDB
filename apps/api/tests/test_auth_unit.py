
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.security import attempt_key, hash_token, normalize_identifier, password_hash
from app.main import app


def test_password_uses_argon2id_and_round_trips() -> None:
    hashed = password_hash.hash("a secure passphrase")
    assert hashed.startswith("$argon2id$")
    assert password_hash.verify("a secure passphrase", hashed)
    assert not password_hash.verify("wrong passphrase", hashed)


def test_identifier_and_attempt_key_are_normalized_and_hmaced() -> None:
    assert normalize_identifier("  ADMIN@Example.COM ") == "admin@example.com"
    assert attempt_key("Admin", "127.0.0.1") == attempt_key(" admin ", "127.0.0.1")
    assert attempt_key("Admin", "127.0.0.1") != attempt_key("Admin", "127.0.0.2")
    assert len(hash_token("session")) == 64


def test_correlation_header_accepts_only_uuid() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health/live", headers={"X-Correlation-ID": "bad\r\nforged"})
    UUID(response.headers["x-correlation-id"])
    response = client.get("/api/v1/health/live", headers={"X-Correlation-ID": "123e4567-e89b-12d3-a456-426614174000"})
    assert response.headers["x-correlation-id"] == "123e4567-e89b-12d3-a456-426614174000"
