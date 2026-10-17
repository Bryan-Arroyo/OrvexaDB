from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    direction: str = Field(pattern="^(in|out)$")
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(pattern="^(purchase|sale|adjustment|return)$")
    description: str | None = Field(default=None, max_length=240)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class MovementView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    user_id: UUID | None
    quantity: Decimal
    direction: str
    reason: str
    description: str | None
    occurred_at: datetime
    product_name: str | None = None
    product_sku: str | None = None


class MovementList(BaseModel):
    items: list[MovementView]
    page: int
    page_size: int
    total: int
