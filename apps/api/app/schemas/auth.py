from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    email: str
    is_active: bool
    must_change_password: bool
    role: str | None = None
    permissions: list[str] = []
    last_login_at: datetime | None = None


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=320)
    role: str = Field(pattern="^(administrator|employee)$")

    @field_validator("username", "email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.strip().lower()


class UpdateUserRequest(BaseModel):
    email: str | None = Field(default=None, min_length=5, max_length=320)
    role: str | None = Field(default=None, pattern="^(administrator|employee)$")

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value


class UserList(BaseModel):
    items: list[UserView]
    page: int
    page_size: int
    total: int
