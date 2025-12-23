"""Gestion PostgreSQL."""
import logging
import asyncpg
from config import DB_CONFIG, HISTORY_LIMIT

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Initialise le pool de connexions et crée les tables."""
    global pool

    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_minimal (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_user
            ON conversations_minimal(user_id, created_at DESC)
        """)

    logger.info("DB connectée")


async def close_db() -> None:
    """Ferme le pool."""
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("DB fermée")


async def get_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    """Récupère l'historique des messages."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM conversations_minimal
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)

    # Reverse pour ordre chronologique
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def save_message(user_id: int, role: str, content: str) -> None:
    """Sauvegarde un message."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_minimal (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)
