from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"
    log_level: str = "INFO"
    auth_pepper: str
    auth_cookie_secure: bool = False
    auth_session_hours: int = 8
    allowed_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with Psycopg 3")
        return value

    @field_validator("auth_pepper")
    @classmethod
    def require_pepper(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("AUTH_PEPPER must be a random value of at least 32 characters")
        return value

    @field_validator("auth_session_hours")
    @classmethod
    def safe_session_hours(cls, value: int) -> int:
        if not 1 <= value <= 8:
            raise ValueError("AUTH_SESSION_HOURS must be between 1 and 8")
        return value

    @model_validator(mode="after")
    def secure_https_origins(self):
        if (self.environment == "production" or any(origin.strip().lower().startswith("https://") for origin in self.allowed_origins.split(","))) and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true when HTTPS origins are configured")
        return self

    @property
    def origin_list(self) -> set[str]:
        return {item.strip().rstrip("/") for item in self.allowed_origins.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
