import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.api.catalog import create_product, deactivate_product, list_products
from app.api.inventory import create_movement
from app.core.security import password_hash
from app.main import app
from app.models.entities import (
    AuditLog,
    Category,
    InventoryMovement,
    Permission,
    Product,
    Role,
    RolePermission,
    Supplier,
    User,
)
from app.schemas.catalog import ProductCreate
from app.schemas.inventory import MovementCreate

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")


@pytest.fixture(scope="module")
def postgres():
    from sqlalchemy.engine import make_url

    database = make_url(TEST_DATABASE_URL).database
    assert database == "orvexadb_test" or database.startswith("orvexadb_test_")
    schema = f"orvexadb_domain_{uuid.uuid4().hex}"
    admin = create_engine(TEST_DATABASE_URL)
    with admin.begin() as connection:
        public_before = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-c search_path={schema}"})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield SessionLocal
    finally:
        engine.dispose()
        with admin.begin() as connection:
            public_after = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
            assert public_after == public_before
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def domain(postgres):
    with postgres.begin() as db:
        role = db.scalar(select(Role).where(Role.name == "administrator"))
        if role is None:
            role = Role(name="administrator")
            db.add(role)
            db.flush()
        permissions = []
        for code in ("product.read", "product.create", "product.update", "product.deactivate", "category.manage", "supplier.manage", "inventory.read", "inventory.move"):
            permission = db.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code)
                db.add(permission)
                db.flush()
            permissions.append(permission)
            if db.scalar(select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)) is None:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        actor = User(username=f"domain_{uuid.uuid4().hex[:8]}", email=f"domain_{uuid.uuid4().hex[:8]}@example.test", password_hash="x", role_id=role.id, must_change_password=False)
        category = Category(code=f"CAT-{uuid.uuid4().hex[:8].upper()}", name="Hardware")
        supplier = Supplier(code=f"SUP-{uuid.uuid4().hex[:8].upper()}", name="Supplier")
        db.add_all([actor, category, supplier])
        db.flush()
        return actor, category, supplier


def _product(db, actor, category, supplier, sku=None):
    return create_product(ProductCreate(sku=sku or f"SKU-{uuid.uuid4().hex[:8].upper()}", name="Keyboard", category_id=category.id, supplier_id=supplier.id, unit_cost="5.00", minimum_stock="2.00"), db, actor)


def test_crud_logical_duplicate_pagination_and_stock_read_only(postgres, domain):
    actor, category, supplier = domain
    with postgres() as db:
        first = _product(db, actor, category, supplier, "SKU-ALPHA")
        _product(db, actor, category, supplier, "SKU-BETA")
        with pytest.raises(HTTPException) as duplicate:
            _product(db, actor, category, supplier, "SKU-ALPHA")
        assert duplicate.value.status_code == 409
        result = list_products(1, 1, "alpha", True, None, None, "sku", "asc", db, actor)
        assert result.total == 1 and result.items[0].sku == "SKU-ALPHA"
        assert first.stock_current == 0
        deactivate_product(first.id, db, actor)
        assert db.get(Product, first.id).is_active is False
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(first.id))) >= 2


def test_inventory_in_out_inactive_insufficient_and_rollback(postgres, domain):
    actor, category, supplier = domain
    with postgres() as db:
        product = _product(db, actor, category, supplier)
        movement = create_movement(MovementCreate(product_id=product.id, direction="in", quantity="3", reason="purchase", description="initial"), db, actor)
        assert movement.description == "initial"
        audit_row = db.scalar(select(AuditLog).where(AuditLog.entity == "inventory_movement", AuditLog.entity_id == str(movement.id)))
        assert audit_row is not None
        with pytest.raises(HTTPException) as insufficient:
            create_movement(MovementCreate(product_id=product.id, direction="out", quantity="4", reason="sale"), db, actor)
        assert insufficient.value.status_code == 409
        assert db.get(Product, product.id).stock_current == 3
        assert db.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.product_id == product.id)) == 1
        db.get(Product, product.id).is_active = False
        db.flush()
        with pytest.raises(HTTPException) as inactive:
            create_movement(MovementCreate(product_id=product.id, direction="in", quantity="1", reason="return"), db, actor)
        assert inactive.value.status_code == 400


def test_concurrent_outputs_lock_product(postgres, domain):
    actor, category, supplier = domain
    with postgres() as db:
        product = _product(db, actor, category, supplier)
        create_movement(MovementCreate(product_id=product.id, direction="in", quantity="1", reason="purchase"), db, actor)

    def withdraw():
        with postgres() as db:
            try:
                create_movement(MovementCreate(product_id=product.id, direction="out", quantity="1", reason="sale"), db, actor)
                return "ok"
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: withdraw(), range(2)))
    assert sorted(results, key=str) == [409, "ok"]
    with postgres() as db:
        assert db.get(Product, product.id).stock_current == 0
        assert db.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.product_id == product.id)) == 2


def test_http_auth_csrf_permissions_and_read_only(postgres, domain):
    actor, category, supplier = domain
    with postgres() as db:
        db.get(User, actor.id).password_hash = password_hash.hash("Strong-password-123")
        db.commit()

    def override_db():
        db = postgres()
        try:
            yield db
        finally:
            db.close()

    from app.db.session import get_db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/products").status_code == 401
            assert client.post("/api/v1/categories", json={"code": "UNAUTH-CAT", "name": "Unauth"}).status_code == 401
            assert client.post("/api/v1/suppliers", json={"code": "UNAUTH-SUP", "name": "Unauth"}).status_code == 401
            login = client.post("/api/v1/auth/login", json={"identifier": actor.username, "password": "Strong-password-123"}, headers={"Origin": "http://localhost:3000"})
            assert login.status_code == 200
            csrf = client.cookies.get("orvexadb_csrf")
            headers = {"Origin": "http://localhost:3000", "x-csrf-token": csrf}
            category_created = client.post("/api/v1/categories", json={"code": "HTTP-CAT", "name": "HTTP"}, headers=headers)
            assert category_created.status_code == 201
            http_category_id = category_created.json()["id"]
            assert client.post("/api/v1/categories", json={"code": "HTTP-CAT", "name": "Duplicate"}, headers=headers).status_code == 409
            assert client.get(f"/api/v1/categories/{http_category_id}").status_code == 200
            assert client.patch(f"/api/v1/categories/{http_category_id}", json={"name": "HTTP edited"}, headers=headers).status_code == 200
            deactivated_category = client.post(f"/api/v1/categories/{http_category_id}/deactivate", headers=headers)
            assert deactivated_category.status_code == 200 and deactivated_category.json()["is_active"] is False
            activated_category = client.post(f"/api/v1/categories/{http_category_id}/activate", headers=headers)
            assert activated_category.status_code == 200 and activated_category.json()["is_active"] is True
            supplier_created = client.post("/api/v1/suppliers", json={"code": "HTTP-SUP", "name": "HTTP supplier"}, headers=headers)
            assert supplier_created.status_code == 201
            http_supplier_id = supplier_created.json()["id"]
            assert client.post("/api/v1/suppliers", json={"code": "HTTP-SUP", "name": "Duplicate"}, headers=headers).status_code == 409
            assert client.get(f"/api/v1/suppliers/{http_supplier_id}").status_code == 200
            assert client.patch(f"/api/v1/suppliers/{http_supplier_id}", json={"name": "HTTP supplier edited"}, headers=headers).status_code == 200
            deactivated_supplier = client.post(f"/api/v1/suppliers/{http_supplier_id}/deactivate", headers=headers)
            assert deactivated_supplier.status_code == 200 and deactivated_supplier.json()["is_active"] is False
            activated_supplier = client.post(f"/api/v1/suppliers/{http_supplier_id}/activate", headers=headers)
            assert activated_supplier.status_code == 200 and activated_supplier.json()["is_active"] is True
            assert client.get("/api/v1/products?page=1&page_size=101").status_code == 422
            assert client.post("/api/v1/products", json={"sku": "HTTP-SKU", "name": "HTTP", "category_id": str(category.id), "supplier_id": str(supplier.id), "stock_current": 99}, headers=headers).status_code == 422
            created = client.post("/api/v1/products", json={"sku": "HTTP-SKU", "name": "HTTP", "category_id": str(category.id), "supplier_id": str(supplier.id)}, headers=headers)
            assert created.status_code == 201
            assert client.post("/api/v1/products", json={"sku": "HTTP-SKU", "name": "Duplicate", "category_id": str(category.id)}, headers=headers).status_code == 409
            assert client.get("/api/v1/products?page=1&page_size=1&sort=sku&direction=asc").status_code == 200
            product_id = created.json()["id"]
            assert client.get(f"/api/v1/products/{product_id}").status_code == 200
            assert client.patch(f"/api/v1/products/{product_id}", json={"name": "HTTP edited"}, headers=headers).status_code == 200
            assert client.post(f"/api/v1/products/{product_id}/deactivate", headers=headers).status_code == 200
            assert client.post(f"/api/v1/products/{product_id}/activate", headers=headers).status_code == 200
            assert client.post(f"/api/v1/categories/{category.id}/deactivate", headers=headers).status_code == 200
            assert client.post("/api/v1/products", json={"sku": "INACTIVE-REF", "name": "Invalid reference", "category_id": str(category.id)}, headers=headers).status_code == 400
            assert client.post(f"/api/v1/categories/{category.id}/activate", headers=headers).status_code == 200
            movement = client.post("/api/v1/inventory-movements", json={"product_id": product_id, "direction": "in", "quantity": "2", "reason": "purchase"}, headers=headers)
            assert movement.status_code == 201
            with postgres() as db:
                audit_before = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "inventory_movement"))
            assert client.post("/api/v1/inventory-movements", json={"product_id": product_id, "direction": "out", "quantity": "99", "reason": "sale"}, headers=headers).status_code == 409
            with postgres() as db:
                assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "inventory_movement")) == audit_before
            listed = client.get("/api/v1/inventory-movements?sort=occurred_at&order=desc")
            assert listed.status_code == 200
            assert all(item["product_sku"] and item["product_name"] for item in listed.json()["items"])
            assert client.get("/api/v1/dashboard/summary").status_code == 200
            with postgres() as db:
                catalog_audits = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id.in_([http_category_id, http_supplier_id, product_id])))
                assert catalog_audits >= 9
    finally:
        app.dependency_overrides.pop(get_db, None)
