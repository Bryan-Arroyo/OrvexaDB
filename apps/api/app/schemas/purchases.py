from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PurchaseLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: UUID
    lines: list[PurchaseLineInput] = Field(min_length=1)


class PurchaseLineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    unit_cost: Decimal
    line_total: Decimal


class PurchaseOrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    supplier_id: UUID
    supplier_name: str
    status: str
    total: Decimal
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseLineView]


class PurchaseOrderList(BaseModel):
    items: list[PurchaseOrderView]
    page: int
    page_size: int
    total: int
