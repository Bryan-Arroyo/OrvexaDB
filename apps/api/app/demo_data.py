"""Datos de demostración idempotentes.

Uso: docker compose exec api python -m app.demo_data
Requiere haber ejecutado antes `alembic upgrade head` y `python -m app.seed`.
No borra ni modifica datos existentes: solo crea lo que falte.
"""

import secrets
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.inventory import create_movement
from app.api.purchases import confirm_order, create_order, receive_order
from app.core.security import audit, password_hash
from app.models.entities import Category, InventoryMovement, Product, PurchaseOrder, Role, Supplier, User
from app.schemas.inventory import MovementCreate
from app.schemas.purchases import PurchaseLineInput, PurchaseOrderInput

CATEGORIES = {"PERIF": "Periféricos", "COMP": "Componentes", "REDES": "Redes", "ALMAC": "Almacenamiento"}

SUPPLIERS = {
    "PROV-ALTAMAR": "Periféricos Altamar S.L.",
    "PROV-NORVEL": "Componentes Norvel S.A.",
    "PROV-CONECTA": "Conecta Redes Ibérica S.L.",
    "PROV-ALMACENA": "Almacena Data Distribución S.L.",
}

# sku, nombre, categoría, proveedor, coste unitario, stock mínimo
PRODUCTS = [
    ("PER-TEC-001", "Teclado mecánico TKL", "PERIF", "PROV-ALTAMAR", "49.90", "10"),
    ("PER-RAT-002", "Ratón inalámbrico ergonómico", "PERIF", "PROV-ALTAMAR", "24.50", "15"),
    ("PER-MON-003", "Monitor IPS 27\" QHD", "PERIF", "PROV-ALTAMAR", "219.00", "5"),
    ("COM-RAM-004", "Memoria DDR5 32 GB (2x16 GB)", "COMP", "PROV-NORVEL", "94.00", "8"),
    ("COM-FTE-005", "Fuente de alimentación 750 W 80+ Gold", "COMP", "PROV-NORVEL", "89.90", "6"),
    ("COM-DIS-006", "Disipador por aire 120 mm", "COMP", "PROV-NORVEL", "32.00", "10"),
    ("RED-SWI-007", "Switch gestionable 24 puertos", "REDES", "PROV-CONECTA", "159.00", "3"),
    ("RED-ROU-008", "Router Wi-Fi 6 doble banda", "REDES", "PROV-CONECTA", "79.00", "6"),
    ("ALM-SSD-009", "SSD NVMe 1 TB", "ALMAC", "PROV-ALMACENA", "69.90", "12"),
    ("ALM-HDD-010", "Disco duro 4 TB 5400 rpm", "ALMAC", "PROV-ALMACENA", "84.00", "6"),
]

# usuario que registra, sku, dirección, cantidad, motivo, descripción (única: hace de clave de idempotencia)
MOVEMENTS = [
    ("admin", "PER-TEC-001", "in", "25", "adjustment", "Demo: inventario inicial teclados"),
    ("admin", "PER-RAT-002", "in", "40", "adjustment", "Demo: inventario inicial ratones"),
    ("admin", "PER-MON-003", "in", "12", "adjustment", "Demo: inventario inicial monitores"),
    ("admin", "COM-RAM-004", "in", "18", "adjustment", "Demo: inventario inicial memoria"),
    ("admin", "COM-FTE-005", "in", "10", "adjustment", "Demo: inventario inicial fuentes"),
    ("admin", "COM-DIS-006", "in", "22", "adjustment", "Demo: inventario inicial disipadores"),
    ("admin", "RED-SWI-007", "in", "4", "adjustment", "Demo: inventario inicial switches"),
    ("admin", "RED-ROU-008", "in", "14", "adjustment", "Demo: inventario inicial routers"),
    ("admin", "ALM-SSD-009", "in", "20", "adjustment", "Demo: inventario inicial SSD"),
    ("admin", "ALM-HDD-010", "in", "9", "adjustment", "Demo: inventario inicial discos duros"),
    ("employee", "PER-TEC-001", "out", "6", "sale", "Demo: venta mostrador ticket 1042"),
    ("employee", "PER-RAT-002", "out", "12", "sale", "Demo: pedido web 2087"),
    ("employee", "PER-MON-003", "out", "3", "sale", "Demo: venta a cliente empresa"),
    ("employee", "RED-SWI-007", "out", "2", "sale", "Demo: instalación oficina cliente"),
    ("employee", "ALM-SSD-009", "out", "10", "sale", "Demo: pedido web 2101"),
    ("employee", "RED-ROU-008", "out", "4", "sale", "Demo: venta mostrador ticket 1057"),
    ("employee", "PER-TEC-001", "in", "1", "return", "Demo: devolución cliente, embalaje abierto"),
    ("employee", "PER-MON-003", "in", "1", "return", "Demo: devolución dentro de plazo"),
    ("admin", "COM-FTE-005", "out", "1", "adjustment", "Demo: unidad dañada en almacén"),
]

# proveedor, estado final, líneas (sku, cantidad, coste unitario). Una orden demo por proveedor.
ORDERS = [
    ("PROV-CONECTA", "draft", [("RED-SWI-007", "6", "152.00"), ("RED-ROU-008", "8", "75.50")]),
    ("PROV-ALMACENA", "confirmed", [("ALM-SSD-009", "30", "66.50"), ("ALM-HDD-010", "10", "80.00")]),
    ("PROV-ALTAMAR", "received", [("PER-TEC-001", "10", "47.50"), ("PER-RAT-002", "20", "22.90")]),
]

USERS = [("admin", "admin.demo", "admin.demo@orvexa.com", "administrator"), ("employee", "empleado.demo", "empleado.demo@orvexa.com", "employee")]


def _get_or_create(db: Session, model, lookup: dict, values: dict) -> tuple[object, bool]:
    item = db.scalar(select(model).filter_by(**lookup))
    if item is not None:
        return item, False
    item = model(**lookup, **values)
    db.add(item)
    db.flush()
    return item, True


def load(factory: sessionmaker) -> dict:
    counts = {"categories": 0, "suppliers": 0, "products": 0, "users": 0, "movements": 0, "purchase_orders": 0}
    passwords: dict[str, str] = {}
    with factory() as db:
        users: dict[str, User] = {}
        for key, username, email, role_name in USERS:
            role = db.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                raise RuntimeError("roles are not seeded; run python -m app.seed first")
            user = db.scalar(select(User).where(User.username == username))
            if user is None:
                password = secrets.token_urlsafe(12)
                # Cuenta de demostración: se entrega lista para iniciar sesión en la presentación.
                user = User(username=username, email=email, password_hash=password_hash.hash(password), role_id=role.id, must_change_password=False)
                db.add(user)
                db.flush()
                audit(db, user, "demo_user_created", "user", "success", entity_id=str(user.id))
                passwords[username] = password
                counts["users"] += 1
            users[key] = user
        categories = {}
        for code, name in CATEGORIES.items():
            categories[code], created = _get_or_create(db, Category, {"code": code}, {"name": name})
            counts["categories"] += created
        suppliers = {}
        for code, name in SUPPLIERS.items():
            suppliers[code], created = _get_or_create(db, Supplier, {"code": code}, {"name": name})
            counts["suppliers"] += created
        products = {}
        for sku, name, category, supplier, cost, minimum in PRODUCTS:
            values = {"name": name, "category_id": categories[category].id, "supplier_id": suppliers[supplier].id, "unit_cost": Decimal(cost), "minimum_stock": Decimal(minimum), "stock_current": Decimal("0")}
            products[sku], created = _get_or_create(db, Product, {"sku": sku}, values)
            counts["products"] += created
        db.commit()

        # Movimientos y compras pasan por los mismos endpoints que la API: validan stock, auditan y confirman.
        for actor, sku, direction, quantity, reason, description in MOVEMENTS:
            if db.scalar(select(InventoryMovement.id).where(InventoryMovement.product_id == products[sku].id, InventoryMovement.description == description)) is None:
                create_movement(MovementCreate(product_id=products[sku].id, direction=direction, quantity=Decimal(quantity), reason=reason, description=description), db=db, actor=users[actor])
                counts["movements"] += 1

        admin = users["admin"]
        for supplier, target, lines in ORDERS:
            order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.created_by == admin.id, PurchaseOrder.supplier_id == suppliers[supplier].id))
            if order is None:
                payload = PurchaseOrderInput(supplier_id=suppliers[supplier].id, lines=[PurchaseLineInput(product_id=products[sku].id, quantity=Decimal(qty), unit_cost=Decimal(cost)) for sku, qty, cost in lines])
                order_id = create_order(payload, db=db, actor=admin).id
                counts["purchase_orders"] += 1
            else:
                order_id = order.id
            status = db.get(PurchaseOrder, order_id).status
            if target in {"confirmed", "received"} and status == "draft":
                status = confirm_order(order_id, db=db, actor=admin).status
            if target == "received" and status == "confirmed":
                receive_order(order_id, db=db, actor=admin)
    return {"counts": counts, "passwords": passwords}


def main() -> None:
    from app.db.session import SessionLocal

    result = load(SessionLocal)
    print(f"Demo data completed: {result['counts']}")
    for username, password in result["passwords"].items():
        print(f"Contraseña generada para {username}: {password}")
    if not result["passwords"]:
        print("Los usuarios demo ya existían; sus contraseñas no se muestran de nuevo.")


if __name__ == "__main__":
    main()
