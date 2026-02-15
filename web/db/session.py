"""Async database session factory and FastAPI dependency.

Supports both PostgreSQL (production) and SQLite (local dev).
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.config import get_settings

settings = get_settings()

db_url = settings.database_url

# SQLite: swap driver to aiosqlite and ensure the data directory exists
if db_url.startswith("sqlite"):
    db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    # Ensure parent dir exists for the .db file
    db_path = db_url.split("///")[-1]
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(db_url, echo=settings.debug, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(db_url, echo=settings.debug, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
