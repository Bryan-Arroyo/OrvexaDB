from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    search: str | None = Field(default=None, max_length=100)
    sort: str = "name"
    direction: str = Field(default="asc", pattern="^(asc|desc)$")


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("code", "name")
    @classmethod
    def trim(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("code", "name")
    @classmethod
    def trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CategoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryList(BaseModel):
    items: list[CategoryView]
    page: int
    page_size: int
    total: int


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)

    @field_validator("code", "name")
    @classmethod
    def trim(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("code", "name")
    @classmethod
    def trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SupplierView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierList(BaseModel):
    items: list[SupplierView]
    page: int
    page_size: int
    total: int


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    category_id: UUID
    supplier_id: UUID | None = None
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)

    @field_validator("sku", "name")
    @classmethod
    def trim(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: UUID | None = None
    supplier_id: UUID | None = None
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    minimum_stock: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @field_validator("sku", "name")
    @classmethod
    def trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sku: str
    name: str
    category_id: UUID | None
    supplier_id: UUID | None
    stock_current: Decimal
    minimum_stock: Decimal
    unit_cost: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductView]
    page: int
    page_size: int
    total: int
