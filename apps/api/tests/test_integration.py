import os
import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, create_engine, inspect, make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL no configurada; PostgreSQL aislado no disponible",
)


def test_migrations_use_ephemeral_schema_and_constraints():
    database_name = make_url(TEST_DATABASE_URL).database if TEST_DATABASE_URL else None
    assert database_name and (database_name == "orvexadb_test" or database_name.startswith("orvexadb_test_")), "TEST_DATABASE_URL debe apuntar a una base orvexadb_test aislada"
    schema = f"orvexadb_test_{uuid.uuid4().hex}"
    admin = create_engine(TEST_DATABASE_URL)
    scoped = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-c search_path={schema}"})
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        assert connection.execute(text("SELECT current_schema()" )).scalar_one() == "public"
        public_before = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()

    try:
        def run_alembic(revision: str) -> None:
            with scoped.connect() as connection:
                assert connection.execute(text("SELECT current_schema()" )).scalar_one() == schema
                config = Config(str(alembic_ini))
                config.attributes["connection"] = connection
                if revision == "head":
                    command.upgrade(config, revision)
                else:
                    command.downgrade(config, revision)
                connection.commit()

        run_alembic("head")
        with scoped.connect() as connection:
            assert connection.execute(text("SELECT current_schema()" )).scalar_one() == schema
            from app.db.base import Base
            from app.models import entities

            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            for table in Base.metadata.sorted_tables:
                expected = {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)}
                actual = {constraint["name"] for constraint in inspect(connection).get_check_constraints(table.name)}
                assert actual == expected, table.name
        run_alembic("base")
        run_alembic("head")
        with scoped.connect() as connection:
            assert connection.execute(text("SELECT current_schema()" )).scalar_one() == schema
            from app.db.base import Base
            from app.models import entities  # noqa: F401

            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            for table in Base.metadata.sorted_tables:
                expected = {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)}
                actual = {constraint["name"] for constraint in inspect(connection).get_check_constraints(table.name)}
                assert actual == expected, table.name

        from app import seed as seed_module

        original_session_local = seed_module.SessionLocal
        seed_module.SessionLocal = sessionmaker(bind=scoped, autoflush=False, expire_on_commit=False)
        try:
            first = seed_module.seed()
            second = seed_module.seed()
        finally:
            seed_module.SessionLocal = original_session_local

        assert first["roles"] == 2 and first["movements"] == 1
        assert second["roles"] == 0 and second["movements"] == 0
        with scoped.connect() as connection:
            assert connection.execute(text("SELECT current_schema()" )).scalar_one() == schema
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("INSERT INTO products (id, sku, name, stock_current) VALUES ('00000000-0000-0000-0000-000000000002', 'DEMO-001', 'Duplicate', 1)"))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("INSERT INTO products (id, sku, name, stock_current, minimum_stock, unit_cost) VALUES ('00000000-0000-0000-0000-000000000003', 'DEMO-002', 'Negative stock', 0, -1, 0)"))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("INSERT INTO products (id, sku, name, stock_current, minimum_stock, unit_cost) VALUES ('00000000-0000-0000-0000-000000000004', 'DEMO-003', 'Negative cost', 0, 0, -1)"))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("INSERT INTO products (id, sku, name, stock_current, minimum_stock, unit_cost) VALUES ('00000000-0000-0000-0000-000000000005', 'DEMO-004', 'Negative stock', -1, 0, 0)"))
            product_id = connection.execute(text("SELECT id FROM products WHERE sku = 'DEMO-001'")).scalar_one()
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("INSERT INTO inventory_movements (id, product_id, quantity, direction, reason) VALUES ('00000000-0000-0000-0000-000000000012', :product_id, -1, 'in', 'adjustment')"), {"product_id": product_id})
            stock = connection.execute(text("SELECT stock_current FROM products WHERE id = :product_id"), {"product_id": product_id}).scalar_one()
            movement_total = connection.execute(text("SELECT coalesce(sum(CASE WHEN direction = 'in' THEN quantity ELSE -quantity END), 0) FROM inventory_movements WHERE product_id = :product_id"), {"product_id": product_id}).scalar_one()
            assert stock == movement_total

        with admin.begin() as connection:
            assert connection.execute(text("SELECT current_schema()" )).scalar_one() == "public"
            public_after = connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")).scalars().all()
            assert public_after == public_before
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        scoped.dispose()
        admin.dispose()
