"""Database configuration and utilities."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base  # from .models.base


def get_database_url() -> str:
    """Get database URL from environment or use default SQLite."""
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")


def create_engine_and_session(database_url: str | None = None):
    """Create async engine and session factory."""
    url = database_url or get_database_url()

    engine = create_async_engine(
        url,
        echo=os.getenv("DEBUG", "").lower() == "true",
        pool_pre_ping=True,
    )

    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return engine, AsyncSessionLocal


async def get_db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine):
    """Initialize database - create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
