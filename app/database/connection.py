"""Database connection management.

SAFETY INVARIANT:
The Cryvex ShopFlow Voice AI Backend does NOT maintain a separate authoritative
product database. All authoritative product and billing data resides in the
main ShopFlow PostgreSQL database accessed via internal API.

This module provides optional connection pooling for non-authoritative local
caching or voice audit logs if DATABASE_URL is configured.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from app.core.config import settings
from app.core.logging import logger

_engine: Optional[AsyncEngine] = None


def get_db_engine() -> Optional[AsyncEngine]:
    """Returns database engine if DATABASE_URL is configured."""
    global _engine
    if _engine is None and settings.DATABASE_URL:
        # Convert postgres:// to postgresql+psycopg:// if necessary
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

        try:
            _engine = create_async_engine(db_url, pool_size=5, max_overflow=2, echo=False)
            logger.info("Database connection engine initialized successfully")
        except Exception as e:
            logger.warning(f"Could not initialize database engine: {e}")
            _engine = None
    return _engine


async def check_db_health() -> bool:
    """Checks optional database connectivity."""
    engine = get_db_engine()
    if engine is None:
        return True  # Optional DB not configured; system functions in decoupled internal API mode
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False
