"""Create the immutable initial schema."""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE roles (id UUID PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    op.execute("CREATE TABLE permissions (id UUID PRIMARY KEY, code VARCHAR(100) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    op.execute("CREATE TABLE role_permissions (role_id UUID NOT NULL REFERENCES roles(id), permission_id UUID NOT NULL REFERENCES permissions(id), PRIMARY KEY(role_id, permission_id))")
    op.execute("CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, email VARCHAR(320) NOT NULL UNIQUE, password_hash VARCHAR(255), is_active BOOLEAN NOT NULL DEFAULT TRUE, role_id UUID REFERENCES roles(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_users_username_normalized CHECK (username = lower(username)), CONSTRAINT ck_users_email_normalized CHECK (email = lower(email)))")
    op.execute("CREATE TABLE user_sessions (id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id), token_hash VARCHAR(128) NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ)")
    op.execute("CREATE TABLE categories (id UUID PRIMARY KEY, code VARCHAR(40) NOT NULL UNIQUE, name VARCHAR(120) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_categories_code_normalized CHECK (code = upper(code)))")
    op.execute("CREATE TABLE suppliers (id UUID PRIMARY KEY, code VARCHAR(40) NOT NULL UNIQUE, name VARCHAR(160) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_suppliers_code_normalized CHECK (code = upper(code)))")
    op.execute("CREATE TABLE products (id UUID PRIMARY KEY, sku VARCHAR(80) NOT NULL UNIQUE, name VARCHAR(160) NOT NULL, category_id UUID REFERENCES categories(id), supplier_id UUID REFERENCES suppliers(id), stock_current NUMERIC(12,2) NOT NULL DEFAULT 0, minimum_stock NUMERIC(12,2) NOT NULL DEFAULT 0, unit_cost NUMERIC(12,2) NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_products_stock_nonnegative CHECK (stock_current >= 0), CONSTRAINT ck_products_minimum_stock_nonnegative CHECK (minimum_stock >= 0), CONSTRAINT ck_products_unit_cost_nonnegative CHECK (unit_cost >= 0), CONSTRAINT ck_products_sku_normalized CHECK (sku = upper(sku)))")
    op.execute("CREATE TABLE inventory_movements (id UUID PRIMARY KEY, product_id UUID NOT NULL REFERENCES products(id), user_id UUID REFERENCES users(id), quantity NUMERIC(12,2) NOT NULL, direction VARCHAR(8) NOT NULL, reason VARCHAR(30) NOT NULL, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_movements_quantity_positive CHECK (quantity > 0), CONSTRAINT ck_movements_direction CHECK (direction IN ('in','out')), CONSTRAINT ck_movements_reason CHECK (reason IN ('purchase','sale','adjustment','return')))")
    op.execute("CREATE INDEX ix_inventory_movements_product_id ON inventory_movements(product_id)")
    op.execute("CREATE TABLE audit_logs (id UUID PRIMARY KEY, actor_user_id UUID REFERENCES users(id), action VARCHAR(80) NOT NULL, entity VARCHAR(80) NOT NULL, entity_id VARCHAR(100), result VARCHAR(30) NOT NULL, metadata_json JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    op.execute("CREATE TABLE data_jobs (id UUID PRIMARY KEY, job_type VARCHAR(30) NOT NULL, status VARCHAR(30) NOT NULL, processed_count INTEGER NOT NULL DEFAULT 0, accepted_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_data_jobs_processed_nonnegative CHECK (processed_count >= 0), CONSTRAINT ck_data_jobs_accepted_nonnegative CHECK (accepted_count >= 0), CONSTRAINT ck_data_jobs_rejected_nonnegative CHECK (rejected_count >= 0))")
    op.execute("CREATE TABLE data_job_errors (id UUID PRIMARY KEY, job_id UUID NOT NULL REFERENCES data_jobs(id), row_number INTEGER NOT NULL, field VARCHAR(80), message TEXT NOT NULL, CONSTRAINT ck_data_job_errors_row_positive CHECK (row_number > 0))")
    op.execute("CREATE TABLE backup_runs (id UUID PRIMARY KEY, checksum VARCHAR(128), size_bytes INTEGER, status VARCHAR(30) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_backup_runs_size_nonnegative CHECK (size_bytes IS NULL OR size_bytes >= 0))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_job_errors")
    op.execute("DROP TABLE IF EXISTS data_jobs")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS inventory_movements")
    op.execute("DROP TABLE IF EXISTS products")
    op.execute("DROP TABLE IF EXISTS suppliers")
    op.execute("DROP TABLE IF EXISTS categories")
    op.execute("DROP TABLE IF EXISTS user_sessions")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS permissions")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS backup_runs")
