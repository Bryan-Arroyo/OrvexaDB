import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uid()
    name: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = uid()
    code: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uid()
    username: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("username = lower(username)", name="ck_users_username_normalized"), CheckConstraint("email = lower(email)", name="ck_users_email_normalized"))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = uid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
        Index("ix_user_sessions_token_hash", "token_hash"),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[uuid.UUID] = uid()
    key_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        Index("ix_login_attempts_key_hmac", "key_hmac"),
        CheckConstraint("failure_count >= 0", name="ck_login_attempts_failure_nonnegative"),
    )


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = uid()
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("code = upper(code)", name="ck_categories_code_normalized"), Index("ix_categories_active_name", "is_active", "name"))


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[uuid.UUID] = uid()
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("code = upper(code)", name="ck_suppliers_code_normalized"), Index("ix_suppliers_active_name", "is_active", "name"))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = uid()
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    stock_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("stock_current >= 0", name="ck_products_stock_nonnegative"), CheckConstraint("minimum_stock >= 0", name="ck_products_minimum_stock_nonnegative"), CheckConstraint("unit_cost >= 0", name="ck_products_unit_cost_nonnegative"), CheckConstraint("sku = upper(sku)", name="ck_products_sku_normalized"), Index("ix_products_active_name", "is_active", "name"), Index("ix_products_category_id", "category_id"), Index("ix_products_supplier_id", "supplier_id"))


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[uuid.UUID] = uid()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(240))
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_order_lines.id"), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_movements_quantity_positive"), CheckConstraint("direction IN ('in', 'out')", name="ck_movements_direction"), CheckConstraint("reason IN ('purchase', 'sale', 'adjustment', 'return')", name="ck_movements_reason"), Index("ix_inventory_movements_product_id", "product_id"), Index("ix_inventory_movements_occurred_at", "occurred_at"))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[uuid.UUID] = uid()
    order_number: Mapped[str] = mapped_column(String(40), unique=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    supplier_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed', 'received', 'canceled')", name="ck_purchase_orders_status"),
        CheckConstraint("total >= 0", name="ck_purchase_orders_total_nonnegative"),
        Index("ix_purchase_orders_supplier_id", "supplier_id"),
        Index("ix_purchase_orders_status", "status"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    id: Mapped[uuid.UUID] = uid()
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    product_sku: Mapped[str] = mapped_column(String(80))
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_lines_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_lines_cost_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_purchase_lines_total_nonnegative"),
        Index("ix_purchase_order_lines_order_id", "purchase_order_id"),
        Index("ix_purchase_order_lines_product_id", "product_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = uid()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(30))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataJob(Base):
    __tablename__ = "data_jobs"
    id: Mapped[uuid.UUID] = uid()
    job_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("processed_count >= 0", name="ck_data_jobs_processed_nonnegative"), CheckConstraint("accepted_count >= 0", name="ck_data_jobs_accepted_nonnegative"), CheckConstraint("rejected_count >= 0", name="ck_data_jobs_rejected_nonnegative"))


class DataJobError(Base):
    __tablename__ = "data_job_errors"
    id: Mapped[uuid.UUID] = uid()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_jobs.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    field: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("row_number > 0", name="ck_data_job_errors_row_positive"),)


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[uuid.UUID] = uid()
    checksum: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_backup_runs_size_nonnegative"),)
