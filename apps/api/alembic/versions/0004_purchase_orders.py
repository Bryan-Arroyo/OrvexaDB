"""Add purchase orders and idempotent receipt links."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_purchase_orders"
down_revision = "0003_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("supplier_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'confirmed', 'received', 'canceled')", name="ck_purchase_orders_status"),
        sa.CheckConstraint("total >= 0", name="ck_purchase_orders_total_nonnegative"),
        sa.UniqueConstraint("order_number"),
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_sku", sa.String(80), nullable=False),
        sa.Column("product_name", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_lines_quantity_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchase_lines_cost_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_purchase_lines_total_nonnegative"),
    )
    op.create_index("ix_purchase_order_lines_order_id", "purchase_order_lines", ["purchase_order_id"])
    op.create_index("ix_purchase_order_lines_product_id", "purchase_order_lines", ["product_id"])
    op.add_column("inventory_movements", sa.Column("purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_inventory_movements_purchase_order_line", "inventory_movements", "purchase_order_lines", ["purchase_order_line_id"], ["id"])
    op.create_unique_constraint("uq_inventory_movements_purchase_order_line", "inventory_movements", ["purchase_order_line_id"])


def downgrade() -> None:
    op.drop_constraint("uq_inventory_movements_purchase_order_line", "inventory_movements", type_="unique")
    op.drop_constraint("fk_inventory_movements_purchase_order_line", "inventory_movements", type_="foreignkey")
    op.drop_column("inventory_movements", "purchase_order_line_id")
    op.drop_index("ix_purchase_order_lines_product_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_order_id", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
