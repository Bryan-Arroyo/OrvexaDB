import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from app.api.purchases import cancel_order, confirm_order, create_order, receive_order, replace_order
from app.api.dashboard import summary
from app.core.security import password_hash
from app.db.session import get_db
from app.main import app
from app.models.entities import AuditLog, Category, InventoryMovement, Permission, Product, PurchaseOrder, PurchaseOrderLine, Role, RolePermission, Supplier, User
from app.schemas.purchases import PurchaseLineInput, PurchaseOrderInput

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")


@pytest.fixture(scope="module")
def postgres():
    from sqlalchemy.engine import make_url
    database = make_url(TEST_DATABASE_URL).database
    assert database == "orvexadb_test" or database.startswith("orvexadb_test_")
    schema = f"orvexa_purchase_{uuid.uuid4().hex}"
    admin = create_engine(TEST_DATABASE_URL)
    with admin.begin() as connection:
        before = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-c search_path={schema}"})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            assert connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all() == before
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def purchase_domain(postgres):
    with postgres.begin() as db:
        admin_role = Role(name=f"purchase_admin_{uuid.uuid4().hex[:8]}")
        employee_role = Role(name=f"purchase_employee_{uuid.uuid4().hex[:8]}")
        db.add_all([admin_role, employee_role])
        db.flush()
        for code in ("purchase.read", "purchase.manage", "purchase.receive"):
            permission = db.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code)
                db.add(permission)
                db.flush()
            db.add(RolePermission(role_id=admin_role.id, permission_id=permission.id))
            if code != "purchase.manage":
                db.add(RolePermission(role_id=employee_role.id, permission_id=permission.id))
        admin = User(username=f"purchase_{uuid.uuid4().hex[:8]}", email=f"purchase_{uuid.uuid4().hex[:8]}@example.test", password_hash=password_hash.hash("Strong-password-123"), role_id=admin_role.id, must_change_password=False)
        employee = User(username=f"employee_{uuid.uuid4().hex[:8]}", email=f"employee_{uuid.uuid4().hex[:8]}@example.test", password_hash=password_hash.hash("Strong-password-123"), role_id=employee_role.id, must_change_password=False)
        category = Category(code=f"PUR-{uuid.uuid4().hex[:8].upper()}", name="Purchases")
        supplier = Supplier(code=f"SUP-{uuid.uuid4().hex[:8].upper()}", name="Supplier snapshot")
        db.add_all([admin, employee, category, supplier])
        db.flush()
        products = [Product(sku=f"PUR-{uuid.uuid4().hex[:8].upper()}-{i}", name=f"Product {i}", category_id=category.id, supplier_id=supplier.id, stock_current=0, unit_cost=Decimal("1.00")) for i in range(2)]
        db.add_all(products)
        db.flush()
        db.commit()
        return admin, employee, supplier, products


def _payload(supplier, products, quantity="2.00", cost="3.25"):
    return PurchaseOrderInput(supplier_id=supplier.id, lines=[PurchaseLineInput(product_id=products[0].id, quantity=quantity, unit_cost=cost), PurchaseLineInput(product_id=products[1].id, quantity="1.00", unit_cost="0")])


def test_purchase_lifecycle_snapshots_totals_transitions_and_idempotency(postgres, purchase_domain):
    admin, _, supplier, products = purchase_domain
    with postgres() as db:
        order = create_order(_payload(supplier, products), db, admin)
        assert order.number.startswith("PO-") and order.total == Decimal("6.50")
        assert any(line.product_sku == products[0].sku for line in order.lines)
        supplier.name = "Changed supplier"
        products[0].name = "Changed product"
        db.commit()
        order = confirm_order(order.id, db, admin)
        with pytest.raises(HTTPException) as edited:
            replace_order(order.id, _payload(supplier, products), db, admin)
        assert edited.value.status_code == 409
        assert order.status == "confirmed"
        received = receive_order(order.id, db, admin)
        assert received.status == "received"
        assert received.lines[0].product_name != products[0].name
        assert db.get(Product, products[0].id).stock_current == 2
        assert db.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.purchase_order_line_id.is_not(None))) == 2
        receive_order(order.id, db, admin)
        assert db.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.purchase_order_line_id.is_not(None))) == 2
        dashboard = summary(db, admin)
        assert dashboard.recent_movements[0].product_name and dashboard.recent_movements[0].product_sku


def test_purchase_validation_cancel_and_atomic_failure(postgres, purchase_domain, monkeypatch):
    admin, _, supplier, products = purchase_domain
    with postgres() as db:
        supplier = db.get(Supplier, supplier.id)
        products = [db.get(Product, product.id) for product in products]
        with pytest.raises(ValidationError):
            create_order(PurchaseOrderInput(supplier_id=supplier.id, lines=[PurchaseLineInput(product_id=products[0].id, quantity="1", unit_cost="1.001")]), db, admin)
        with pytest.raises(ValidationError):
            PurchaseLineInput(product_id=products[0].id, quantity="0", unit_cost="1")
        with pytest.raises(ValidationError):
            PurchaseLineInput(product_id=products[0].id, quantity="1", unit_cost="-1")
        supplier.is_active = False
        db.flush()
        with pytest.raises(HTTPException) as inactive_supplier:
            create_order(_payload(supplier, products), db, admin)
        assert inactive_supplier.value.status_code == 400
        supplier.is_active = True
        products[0].is_active = False
        db.flush()
        with pytest.raises(HTTPException) as inactive_product:
            create_order(_payload(supplier, products), db, admin)
        assert inactive_product.value.status_code == 400
        products[0].is_active = True
        db.flush()
        order = create_order(_payload(supplier, products), db, admin)
        cancel_order(order.id, db, admin)
        with pytest.raises(HTTPException) as confirmed:
            confirm_order(order.id, db, admin)
        assert confirmed.value.status_code == 409
        order = create_order(_payload(supplier, products), db, admin)
        confirm_order(order.id, db, admin)
        cancel_order(order.id, db, admin)
        with pytest.raises(HTTPException) as canceled_receive:
            receive_order(order.id, db, admin)
        assert canceled_receive.value.status_code == 409
        order = create_order(_payload(supplier, products), db, admin)
        confirm_order(order.id, db, admin)
        original_add = db.add
        stock_before = [product.stock_current for product in products]
        movement_adds = 0
        def fail_add(value, *args, **kwargs):
            nonlocal movement_adds
            if isinstance(value, InventoryMovement):
                movement_adds += 1
                if movement_adds == 2:
                    raise RuntimeError("forced receipt failure")
            return original_add(value, *args, **kwargs)
        monkeypatch.setattr(db, "add", fail_add)
        with pytest.raises(RuntimeError):
            receive_order(order.id, db, admin)
        db.rollback()
        assert db.get(PurchaseOrder, order.id).status == "confirmed"
        assert [db.get(Product, product.id).stock_current for product in products] == stock_before
        assert db.scalar(select(func.count()).select_from(InventoryMovement).join(PurchaseOrderLine, PurchaseOrderLine.id == InventoryMovement.purchase_order_line_id).where(PurchaseOrderLine.purchase_order_id == order.id)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "purchase_order", AuditLog.entity_id == str(order.id), AuditLog.action == "purchase_order_received")) == 0


def test_purchase_permissions_and_concurrent_receive(postgres, purchase_domain):
    admin, employee, supplier, products = purchase_domain
    with postgres() as db:
        order = create_order(_payload(supplier, products), db, admin)
        confirm_order(order.id, db, admin)
    def receive():
        with postgres() as db:
            return receive_order(order.id, db, admin).status
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: receive(), range(2)))
    with postgres() as db:
        assert results == ["received", "received"]
        assert db.scalar(select(func.count()).select_from(InventoryMovement).join(PurchaseOrderLine, PurchaseOrderLine.id == InventoryMovement.purchase_order_line_id).where(PurchaseOrderLine.purchase_order_id == order.id)) == 2
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "purchase_order", AuditLog.entity_id == str(order.id), AuditLog.action == "purchase_order_received")) == 1

def test_purchase_http_permissions(postgres, purchase_domain):
    from fastapi.testclient import TestClient
    admin, employee, supplier, products = purchase_domain
    def override_db():
        db = postgres()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as unauthenticated:
            assert unauthenticated.get("/api/v1/purchase-orders").status_code == 401
        with TestClient(app) as employee_client:
            login = employee_client.post("/api/v1/auth/login", json={"identifier": employee.username, "password": "Strong-password-123"}, headers={"Origin": "http://localhost:3000"})
            assert login.status_code == 200
            csrf = employee_client.cookies.get("orvexadb_csrf")
            headers = {"Origin": "http://localhost:3000", "x-csrf-token": csrf}
            assert employee_client.get("/api/v1/purchase-orders", headers=headers).status_code == 200
            assert employee_client.post("/api/v1/purchase-orders", json={"supplier_id": str(supplier.id), "lines": [{"product_id": str(products[0].id), "quantity": "1", "unit_cost": "1"}]}, headers=headers).status_code == 403
        with TestClient(app) as admin_client:
            login = admin_client.post("/api/v1/auth/login", json={"identifier": admin.username, "password": "Strong-password-123"}, headers={"Origin": "http://localhost:3000"})
            assert login.status_code == 200
            csrf = admin_client.cookies.get("orvexadb_csrf")
            headers = {"Origin": "http://localhost:3000", "x-csrf-token": csrf}
            created = admin_client.post("/api/v1/purchase-orders", json={"supplier_id": str(supplier.id), "lines": [{"product_id": str(products[0].id), "quantity": "1", "unit_cost": "1"}]}, headers=headers)
            assert created.status_code == 201
    finally:
        app.dependency_overrides.pop(get_db, None)
