import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.demo_data import load
from app.models.entities import InventoryMovement, Product, PurchaseOrder, Role, User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")


@pytest.fixture
def factory():
    database = make_url(TEST_DATABASE_URL).database
    assert database == "orvexadb_test" or database.startswith("orvexadb_test_")
    schema = f"orvexa_demo_{uuid.uuid4().hex}"
    admin = create_engine(TEST_DATABASE_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-c search_path={schema}"})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as db:
        db.add_all([Role(name="administrator"), Role(name="employee")])
    try:
        yield sessions
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _snapshot(db):
    return (
        db.scalar(select(func.count()).select_from(Product)),
        db.scalar(select(func.count()).select_from(InventoryMovement)),
        db.scalar(select(func.count()).select_from(User)),
        sorted(db.scalars(select(PurchaseOrder.status)).all()),
        sorted((sku, stock) for sku, stock in db.execute(select(Product.sku, Product.stock_current)).all()),
    )


def test_demo_data_is_idempotent(factory):
    first = load(factory)
    assert set(first["passwords"]) == {"admin.demo", "empleado.demo"}
    with factory() as db:
        before = _snapshot(db)
        low = db.scalar(select(func.count()).select_from(Product).where(Product.stock_current <= Product.minimum_stock))
        keyboard = db.scalar(select(Product).where(Product.sku == "PER-TEC-001"))
    assert before[0] == 10 and before[2] == 2
    assert before[3] == ["confirmed", "draft", "received"]
    assert low == 2
    # 25 inicial - 6 venta + 1 devolución + 10 recibidas en la orden
    assert keyboard.stock_current == Decimal("30.00")

    second = load(factory)
    assert second["passwords"] == {}
    assert all(value == 0 for value in second["counts"].values())
    with factory() as db:
        assert _snapshot(db) == before
