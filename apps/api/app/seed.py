from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import (
    Category,
    InventoryMovement,
    Permission,
    Product,
    Role,
    RolePermission,
    Supplier,
)

PERMISSIONS = ["product.read", "product.create", "product.update", "product.deactivate", "category.manage", "supplier.manage", "inventory.read", "inventory.move", "purchase.read", "purchase.manage", "purchase.receive", "data.import", "data.export", "user.manage", "audit.read", "backup.create", "backup.restore", "settings.manage"]
EMPLOYEE = {"product.read", "product.create", "product.update", "inventory.read", "inventory.move", "purchase.read", "purchase.receive", "data.export"}


def get_or_create(db, model, lookup: dict, values: dict | None = None):
    item = db.scalar(select(model).filter_by(**lookup))
    if item is None:
        item = model(**lookup, **(values or {}))
        db.add(item)
        db.flush()
        return item, True
    return item, False


def seed() -> dict[str, int]:
    counts = {"roles": 0, "permissions": 0, "categories": 0, "suppliers": 0, "products": 0, "movements": 0}
    with SessionLocal.begin() as db:
        admin, created = get_or_create(db, Role, {"name": "administrator"})
        counts["roles"] += created
        employee, created = get_or_create(db, Role, {"name": "employee"})
        counts["roles"] += created
        for code in PERMISSIONS:
            permission, created = get_or_create(db, Permission, {"code": code})
            counts["permissions"] += created
            if db.scalar(select(RolePermission).where(RolePermission.role_id == admin.id, RolePermission.permission_id == permission.id)) is None:
                db.add(RolePermission(role_id=admin.id, permission_id=permission.id))
            if code in EMPLOYEE and db.scalar(select(RolePermission).where(RolePermission.role_id == employee.id, RolePermission.permission_id == permission.id)) is None:
                db.add(RolePermission(role_id=employee.id, permission_id=permission.id))
        category, created = get_or_create(db, Category, {"code": "DEMO-HARDWARE"}, {"name": "Demo hardware"})
        counts["categories"] += created
        supplier, created = get_or_create(db, Supplier, {"code": "DEMO-SUPPLIER"}, {"name": "Demo supplier"})
        counts["suppliers"] += created
        product, created = get_or_create(db, Product, {"sku": "DEMO-001"}, {"name": "Demo keyboard", "category_id": category.id, "supplier_id": supplier.id, "stock_current": Decimal("10.00")})
        counts["products"] += created
        if db.scalar(select(InventoryMovement).where(InventoryMovement.product_id == product.id, InventoryMovement.reason == "adjustment")) is None:
            db.add(InventoryMovement(product_id=product.id, quantity=Decimal("10.00"), direction="in", reason="adjustment"))
            counts["movements"] += 1
    return counts


if __name__ == "__main__":
    print(f"Seed completed: {seed()}")
