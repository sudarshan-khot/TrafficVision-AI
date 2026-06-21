"""
Async database session factory for TrafficVision AI.

This module exposes three objects used throughout the backend:

    engine              — ``AsyncEngine`` created from ``DATABASE_URL``
    AsyncSessionLocal   — ``async_sessionmaker`` bound to the engine;
                          each call produces a new ``AsyncSession``
    get_db              — async generator for FastAPI ``Depends()``
                          injection; yields a session and ensures it is
                          closed even if an exception is raised

Usage
-----
Direct use (e.g. in startup code or scripts):

    from app.database.session import AsyncSessionLocal, engine

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))

Dependency injection (FastAPI route handlers):

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.session import get_db

    @router.get("/example")
    async def example_route(db: AsyncSession = Depends(get_db)):
        ...

Requirements
------------
Implements requirement 3.4 — atomic transaction handling with rollback
on constraint failures is delegated to the caller; the session is
created with ``expire_on_commit=False`` so ORM instances remain usable
after a ``commit()`` or ``rollback()`` without re-loading from the DB.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ---------------------------------------------------------------------------
# Engine — pool options are PostgreSQL-only
# ---------------------------------------------------------------------------

_engine_kwargs: dict = {
    "echo": settings.APP_ENV == "development",
    "pool_pre_ping": True,
}
if settings.DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # Loaded ORM objects remain accessible after commit without issuing a
    # new SELECT.  Required because route handlers often read attributes
    # on returned models after the session has been flushed / committed.
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator that yields a database session for dependency injection.

    Typical usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    The session is created fresh for each request and closed in the
    ``finally`` block regardless of whether the handler succeeded or raised
    an exception.  Transaction management (commit / rollback) is left to the
    individual service functions so they can apply the correct atomicity
    boundaries (requirement 3.4).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
