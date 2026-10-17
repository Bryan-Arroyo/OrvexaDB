from app.db.base import Base
from app.models import entities as _entities  # noqa: F401


def test_expected_tables() -> None:
    expected = {"roles", "permissions", "role_permissions", "users", "user_sessions", "categories", "suppliers", "products", "inventory_movements", "purchase_orders", "purchase_order_lines", "audit_logs", "data_jobs", "data_job_errors", "backup_runs"}
    assert expected <= set(Base.metadata.tables)
