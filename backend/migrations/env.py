"""
Alembic environment for BitcoinTX.

The app runs migrations itself at startup (backend/migrations/runner.py),
passing an open connection in config.attributes["connection"]. The `alembic`
CLI (alembic.ini at the repo root) is for developers writing migrations:

    alembic revision --autogenerate --rev-id 0004 -m "add foo to transactions"

SQLite can't ALTER most things in place, so render_as_batch is on: column
changes are emitted as "copy table, swap" batches.
"""

from alembic import context
from sqlalchemy import create_engine

import backend.models  # noqa: F401  (registers every table on Base.metadata)
from backend.database import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    from backend.database import DATABASE_URL

    context.configure(
        url=config.get_main_option("sqlalchemy.url") or DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    from backend.database import DATABASE_URL

    engine = create_engine(config.get_main_option("sqlalchemy.url") or DATABASE_URL)
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
