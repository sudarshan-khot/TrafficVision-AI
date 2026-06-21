"""
Alembic environment script for TrafficVision AI.

Configured for async SQLAlchemy (asyncpg driver).  The database URL is read
from the ``DATABASE_URL`` environment variable (via ``app.config.settings``)
at runtime so that the placeholder value in ``alembic.ini`` is never used for
real connections.

Requirements: 3.5
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the backend package root (the directory that contains the `app`
# package) is on sys.path so that `from app.xxx import ...` works when
# Alembic is invoked from the backend/ directory.
# ---------------------------------------------------------------------------
# This file lives at:  backend/app/database/migrations/env.py
# We need:             backend/   on sys.path
_here = os.path.dirname(os.path.abspath(__file__))           # migrations/
_backend_root = os.path.abspath(os.path.join(_here, "..", "..", ".."))  # backend/
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# ---------------------------------------------------------------------------
# Import ORM Base so that autogenerate can detect all table definitions.
# ---------------------------------------------------------------------------
from app.database.models import Base  # noqa: E402  (import after sys.path fix)

# ---------------------------------------------------------------------------
# Import settings to read DATABASE_URL from the environment.
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Override the sqlalchemy.url in the .ini file with the live DATABASE_URL from
# the environment so that passwords / hostnames never live in version control.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configure Python logging from the [loggers] / [handlers] section of
# alembic.ini when the file is present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata object that autogenerate will compare against the live schema.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In offline mode Alembic emits SQL to stdout (or a file) instead of
    connecting to the database.  Useful for generating migration scripts to
    review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render the CREATE TABLE statements with IF NOT EXISTS so that the
        # offline SQL is safe to re-run.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Apply pending migrations using an already-open synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside a synchronous callback."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,   # single-use connection; no pool needed for migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to a live database)."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
