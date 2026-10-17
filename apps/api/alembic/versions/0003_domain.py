"""Add domain indexes and movement descriptions."""
from alembic import op
import sqlalchemy as sa

revision = "0003_domain"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_movements", sa.Column("description", sa.String(240), nullable=True))
    op.create_index("ix_categories_active_name", "categories", ["is_active", "name"])
    op.create_index("ix_suppliers_active_name", "suppliers", ["is_active", "name"])
    op.create_index("ix_products_active_name", "products", ["is_active", "name"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"])
    op.create_index("ix_inventory_movements_occurred_at", "inventory_movements", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_occurred_at", table_name="inventory_movements")
    op.drop_index("ix_products_supplier_id", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_active_name", table_name="products")
    op.drop_index("ix_suppliers_active_name", table_name="suppliers")
    op.drop_index("ix_categories_active_name", table_name="categories")
    op.drop_column("inventory_movements", "description")
