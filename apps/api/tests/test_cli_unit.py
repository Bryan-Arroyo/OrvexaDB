import pytest

from app.cli.create_admin import prompt_admin
from app.cli import create_admin


def test_create_admin_prompt_normalizes_and_never_accepts_short_password(monkeypatch) -> None:
    answers = iter([" Admin ", "Admin@Example.com", "short", "short"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))
    with pytest.raises(ValueError, match="12 to 128"):
        prompt_admin()


def test_create_admin_prompt_requires_confirmation(monkeypatch) -> None:
    answers = iter(["admin", "admin@example.com", "a secure passphrase", "different passphrase"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))
    with pytest.raises(ValueError, match="do not match"):
        prompt_admin()


def test_create_admin_is_bootstrap_only(monkeypatch) -> None:
    class ExistingAdmin:
        @classmethod
        def begin(cls):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalar(self, _query):
            return ExistingAdmin()

    monkeypatch.setattr(create_admin, "prompt_admin", lambda: ("newadmin", "new@example.com", "a secure passphrase"))
    monkeypatch.setattr(create_admin, "SessionLocal", ExistingAdmin)
    with pytest.raises(ValueError, match="user already exists"):
        create_admin.create_admin()
