"""
Database connection pooling and helpers for Luna Bot.

Usage:
    from core import get_db

    db = await get_db()
    result = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg

from core.logger import get_logger
from core.errors import DatabaseError, with_retry

logger = get_logger(__name__)


class Database:
    """
    Database wrapper with connection pooling and retry logic.
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._config: dict = {}

    async def connect(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "luna",
        password: str = "luna_password",
        database: str = "luna_db",
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        """
        Create connection pool.

        Args:
            host: Database host
            port: Database port
            user: Database user
            password: Database password
            database: Database name
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        self._config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }

        self._pool = await asyncpg.create_pool(
            **self._config,
            min_size=min_size,
            max_size=max_size,
        )

        logger.info(f"Database connected: {host}:{port}/{database}")

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database disconnected")

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool."""
        if not self._pool:
            raise DatabaseError("Database not connected", "pool_access")
        return self._pool

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.

        Usage:
            async with db.acquire() as conn:
                await conn.execute(...)
        """
        async with self.pool.acquire() as conn:
            yield conn

    # =========================================================================
    # QUERY HELPERS WITH RETRY
    # =========================================================================

    @with_retry(max_attempts=3, delay=0.5, exceptions=(asyncpg.PostgresError,))
    async def execute(self, query: str, *args) -> str:
        """Execute a query (INSERT, UPDATE, DELETE)."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    @with_retry(max_attempts=3, delay=0.5, exceptions=(asyncpg.PostgresError,))
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row."""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @with_retry(max_attempts=3, delay=0.5, exceptions=(asyncpg.PostgresError,))
    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch multiple rows."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    @with_retry(max_attempts=3, delay=0.5, exceptions=(asyncpg.PostgresError,))
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    # =========================================================================
    # SAFE JSON HELPERS
    # =========================================================================

    @staticmethod
    def safe_json_loads(data: Any, fallback: Any = None) -> Any:
        """
        Safely parse JSON, handling both str and dict inputs.

        Args:
            data: JSON string or already-parsed dict
            fallback: Value to return on parse error

        Returns:
            Parsed dict or fallback
        """
        if data is None:
            return fallback
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                import json
                return json.loads(data)
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Failed to parse JSON: {data[:100]}...")
                return fallback
        return fallback


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_db: Optional[Database] = None


async def get_db() -> Database:
    """
    Get the database singleton.
    Must call init_db() first.
    """
    global _db
    if _db is None:
        raise DatabaseError("Database not initialized. Call init_db() first.", "get_db")
    return _db


async def init_db(
    host: str = "localhost",
    port: int = 5432,
    user: str = "luna",
    password: str = "luna_password",
    database: str = "luna_db",
    **kwargs,
) -> Database:
    """
    Initialize the database singleton.

    Args:
        host: Database host
        port: Database port
        user: Database user
        password: Database password
        database: Database name
        **kwargs: Additional pool options

    Returns:
        Database instance
    """
    global _db
    if _db is not None:
        return _db

    _db = Database()
    await _db.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        **kwargs,
    )
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.disconnect()
        _db = None
