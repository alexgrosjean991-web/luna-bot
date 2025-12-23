"""Gestion PostgreSQL."""
import json
import logging
from datetime import datetime, timedelta
import asyncpg
from settings import DB_CONFIG, HISTORY_LIMIT, PARIS_TZ, DB_POOL_MIN, DB_POOL_MAX

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Initialise le pool de connexions et crée les tables."""
    global pool

    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=DB_POOL_MIN, max_size=DB_POOL_MAX)

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

        # Colonnes pour progression relation
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            phase VARCHAR(20) DEFAULT 'discovery'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            first_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            day_count INTEGER DEFAULT 1
        """)

        # Colonnes pour subscription/paywall
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            subscription_status VARCHAR(20) DEFAULT 'trial'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            paywall_sent BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            teasing_stage INTEGER DEFAULT 0
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
    """Récupère ou crée un utilisateur (race-condition safe)."""
    async with pool.acquire() as conn:
        # INSERT ON CONFLICT évite la race condition
        row = await conn.fetchrow("""
            INSERT INTO users (telegram_id)
            VALUES ($1)
            ON CONFLICT (telegram_id) DO UPDATE SET telegram_id = $1
            RETURNING id, telegram_id, memory, total_messages
        """, telegram_id)
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


async def get_user_data(user_id: int) -> dict:
    """Récupère toutes les données utilisateur."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM users WHERE id = $1
        """, user_id)
        return dict(row) if row else {}


async def update_teasing_stage(user_id: int, stage: int) -> None:
    """Met à jour le teasing stage."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET teasing_stage = $1 WHERE id = $2",
            stage, user_id
        )


# Seuils de phase (legacy, gardé pour compatibilité)
PHASE_THRESHOLDS = {
    "discovery": (1, 2),
    "connection": (3, 4),
    "attachment": (5, 7),
    "intimate": (8, 999),
}


async def get_user_phase(user_id: int) -> tuple[str, int]:
    """Calcule la phase actuelle et le jour de relation."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT first_message_at, phase FROM users WHERE id = $1
        """, user_id)

        if not row or not row["first_message_at"]:
            return "hook", 1

        first_msg = row["first_message_at"]
        now = datetime.now(PARIS_TZ)

        # Rendre timezone-aware si nécessaire
        if first_msg.tzinfo is None:
            first_msg = first_msg.replace(tzinfo=PARIS_TZ)

        day_count = (now - first_msg).days + 1

        # Déterminer la phase
        phase = "convert"
        for phase_name, (start, end) in PHASE_THRESHOLDS.items():
            if start <= day_count <= end:
                phase = phase_name
                break

        # Mettre à jour si changé
        if phase != row["phase"]:
            await conn.execute("""
                UPDATE users SET phase = $1, day_count = $2 WHERE id = $3
            """, phase, day_count, user_id)

        return phase, day_count
