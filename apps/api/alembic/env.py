import os
from logging.config import fileConfig

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import engine_from_config, pool

from alembic import context
from app.db.base import Base
from app.models import entities  # noqa: F401  # register every mapped table

config = context.config
if config.config_file_name and all(
    config.get_section(section) for section in ("loggers", "handlers", "formatters")
):
    fileConfig(config.config_file_name)

injected_connection = config.attributes.get("connection")
database_url = os.getenv("DATABASE_URL")
if injected_connection is None:
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when Alembic opens its own connection")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def assert_no_model_drift(connection) -> None:
    differences = compare_metadata(MigrationContext.configure(connection), target_metadata)
    if differences:
        raise RuntimeError(f"Model/migration drift detected: {differences}")


def run_migrations_offline() -> None:
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if injected_connection is not None:
        context.configure(connection=injected_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
