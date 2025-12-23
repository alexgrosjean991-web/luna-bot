"""Gestion PostgreSQL."""
import json
import logging
from datetime import datetime, timedelta, timezone
import asyncpg
from settings import DB_CONFIG, HISTORY_LIMIT

logger = logging.getLogger(__name__)

# Timezone Paris (UTC+1/+2)
PARIS_TZ = timezone(timedelta(hours=1))

pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Initialise le pool de connexions et crée les tables."""
    global pool

    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)

    async with pool.acquire() as conn:
        # Table users avec mémoire
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                memory JSONB DEFAULT '{}',
                total_messages INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram
            ON users(telegram_id)
        """)

        # Ajouter last_active si pas présent
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        """)

        # Table conversations
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

        # Table proactive_log
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                message_type VARCHAR(20) NOT NULL,
                sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_proactive_user_date
            ON proactive_log(user_id, sent_at DESC)
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


async def get_or_create_user(telegram_id: int) -> dict:
    """Récupère ou crée un utilisateur."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, telegram_id, memory, total_messages FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if row:
            return dict(row)

        # Créer le user
        row = await conn.fetchrow(
            """
            INSERT INTO users (telegram_id) VALUES ($1)
            RETURNING id, telegram_id, memory, total_messages
            """,
            telegram_id
        )
        return dict(row)


async def get_user_memory(user_id: int) -> dict:
    """Récupère la mémoire d'un utilisateur."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT memory FROM users WHERE id = $1",
            user_id
        )
        if row and row["memory"]:
            mem = row["memory"]
            return json.loads(mem) if isinstance(mem, str) else mem
        return {}


async def update_user_memory(user_id: int, memory: dict) -> None:
    """Met à jour la mémoire d'un utilisateur."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET memory = $1 WHERE id = $2",
            json.dumps(memory, ensure_ascii=False),
            user_id
        )


async def increment_message_count(user_id: int) -> int:
    """Incrémente et retourne le compteur de messages."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET total_messages = total_messages + 1
            WHERE id = $1
            RETURNING total_messages
            """,
            user_id
        )
        return row["total_messages"] if row else 0


async def update_last_active(user_id: int) -> None:
    """Met à jour last_active (appelé quand user envoie un message)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_active = NOW() WHERE id = $1",
            user_id
        )


async def get_users_for_proactive(inactive_hours: int = 0) -> list[dict]:
    """Récupère les users éligibles aux messages proactifs."""
    now = datetime.now(PARIS_TZ)
    async with pool.acquire() as conn:
        if inactive_hours > 0:
            cutoff = now - timedelta(hours=inactive_hours)
            cutoff_max = now - timedelta(hours=48)
            rows = await conn.fetch("""
                SELECT id, telegram_id, last_active, memory
                FROM users
                WHERE last_active < $1 AND last_active > $2
            """, cutoff, cutoff_max)
        else:
            cutoff = now - timedelta(hours=48)
            rows = await conn.fetch("""
                SELECT id, telegram_id, last_active, memory
                FROM users
                WHERE last_active > $1
            """, cutoff)
        return [dict(row) for row in rows]


async def count_proactive_today(user_id: int) -> int:
    """Compte les messages proactifs envoyés aujourd'hui à ce user."""
    now = datetime.now(PARIS_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as count FROM proactive_log
            WHERE user_id = $1 AND sent_at > $2
        """, user_id, today_start)
        return row["count"] if row else 0


async def log_proactive(user_id: int, message_type: str) -> None:
    """Log un message proactif envoyé."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO proactive_log (user_id, message_type)
            VALUES ($1, $2)
        """, user_id, message_type)
