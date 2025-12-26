"""Gestion PostgreSQL."""
import json
import logging
from datetime import datetime, timedelta
from typing import Any
import asyncpg
from settings import DB_CONFIG, HISTORY_LIMIT, PARIS_TZ, DB_POOL_MIN, DB_POOL_MAX

logger = logging.getLogger(__name__)


def safe_json_loads(data: Any, default: Any = None, context: str = "") -> Any:
    """Parse JSON de manière sécurisée avec fallback."""
    if data is None:
        return default if default is not None else {}
    if not isinstance(data, str):
        return data  # Déjà un dict/list
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON corrompu {context}: {e}")
        return default if default is not None else {}

pool: asyncpg.Pool | None = None


class DatabaseNotInitializedError(Exception):
    """Raised when trying to use DB before init."""
    pass


def get_pool() -> asyncpg.Pool:
    """Retourne le pool, raise si non initialisé."""
    if pool is None:
        raise DatabaseNotInitializedError(
            "Database pool not initialized. Call init_db() first."
        )
    return pool


async def execute_with_retry(query: str, *args, max_retries: int = 3):
    """Execute une requête avec retry en cas d'erreur de connexion."""
    last_error = None
    for attempt in range(max_retries):
        try:
            async with get_pool().acquire() as conn:
                return await conn.execute(query, *args)
        except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
            last_error = e
            logger.warning(f"DB connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_error


async def fetchrow_with_retry(query: str, *args, max_retries: int = 3):
    """Fetch une row avec retry en cas d'erreur de connexion."""
    last_error = None
    for attempt in range(max_retries):
        try:
            async with get_pool().acquire() as conn:
                return await conn.fetchrow(query, *args)
        except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
            last_error = e
            logger.warning(f"DB connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_error


async def init_db() -> None:
    """Initialise le pool de connexions et crée les tables."""
    global pool

    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=DB_POOL_MIN, max_size=DB_POOL_MAX)

    async with get_pool().acquire() as conn:
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

        # Colonne pour préparation paywall (J5)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            preparation_sent BOOLEAN DEFAULT FALSE
        """)

        # CRITICAL FIX: Colonnes pour états persistants (au lieu de mémoire)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            emotional_state VARCHAR(20) DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)

        # V5: Colonnes pour psychology modules
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            inside_jokes JSONB DEFAULT '[]'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            pending_events JSONB DEFAULT '[]'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            attachment_score FLOAT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            session_count INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            user_initiated_count INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            vulnerabilities_shared INTEGER DEFAULT 0
        """)

        # V6: Colonnes pour conversion premium
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            premium_preview_count INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            conversion_shown_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)

        # Colonnes pour session tracking (utilisees par V3 momentum)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            messages_this_session INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_climax_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)

        # V8: Colonnes pour Luna mood system
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            luna_mood VARCHAR(20) DEFAULT 'normal'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            mood_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_horny_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)

        # V3: Colonnes pour momentum system
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            momentum FLOAT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            intimacy_history INT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            messages_since_climax INT DEFAULT 999
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            current_tier INT DEFAULT 1
        """)

        # V7: Colonnes pour Trust system
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            trust_score INTEGER DEFAULT 50
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            luna_last_state VARCHAR(20) DEFAULT 'neutral'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            unlocked_secrets JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_trust_update TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)

        # Phase A: Intent + AHA
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            user_intent VARCHAR(20) DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            aha_triggered BOOLEAN DEFAULT FALSE
        """)

        # Phase B: Gates + Investment
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            gates_triggered JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            investment_score INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            secrets_shared_count INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            compliments_given INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            questions_about_luna INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            user_segment VARCHAR(20) DEFAULT 'casual'
        """)

        # Phase C: Churn + Win-back
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            churn_risk VARCHAR(20) DEFAULT 'low'
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            churn_score FLOAT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_churn_check TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            winback_stage VARCHAR(20) DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_winback_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            winback_attempts INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            peak_hours JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            active_days JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            avg_response_time FLOAT DEFAULT NULL
        """)

        # Photos system
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            photos_sent JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            last_photo_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            photos_count INTEGER DEFAULT 0
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
    async with get_pool().acquire() as conn:
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
    async with get_pool().acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_minimal (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def get_or_create_user(telegram_id: int) -> dict:
    """Récupère ou crée un utilisateur (race-condition safe)."""
    async with get_pool().acquire() as conn:
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
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT memory FROM users WHERE id = $1",
            user_id
        )
        if row and row["memory"]:
            return safe_json_loads(row["memory"], {}, f"memory user {user_id}")
        return {}


async def update_user_memory(user_id: int, memory: dict) -> None:
    """Met à jour la mémoire d'un utilisateur."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET memory = $1 WHERE id = $2",
            json.dumps(memory, ensure_ascii=False),
            user_id
        )


async def increment_message_count(user_id: int) -> int:
    """Incrémente et retourne le compteur de messages."""
    async with get_pool().acquire() as conn:
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
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_active = NOW() WHERE id = $1",
            user_id
        )


async def get_users_for_proactive(inactive_hours: int = 0) -> list[dict]:
    """Récupère les users éligibles aux messages proactifs."""
    now = datetime.now(PARIS_TZ)
    async with get_pool().acquire() as conn:
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
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as count FROM proactive_log
            WHERE user_id = $1 AND sent_at > $2
        """, user_id, today_start)
        return row["count"] if row else 0


async def log_proactive(user_id: int, message_type: str) -> None:
    """Log un message proactif envoyé."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            INSERT INTO proactive_log (user_id, message_type)
            VALUES ($1, $2)
        """, user_id, message_type)


async def get_user_data(user_id: int) -> dict:
    """Récupère toutes les données utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM users WHERE id = $1
        """, user_id)
        return dict(row) if row else {}


async def update_teasing_stage(user_id: int, stage: int) -> None:
    """Met à jour le teasing stage."""
    async with get_pool().acquire() as conn:
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
    async with get_pool().acquire() as conn:
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


# ============== CRITICAL FIX: États persistants ==============

async def get_emotional_state(user_id: int) -> str | None:
    """Récupère l'état émotionnel persistant."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT emotional_state FROM users WHERE id = $1", user_id
        )
        return row["emotional_state"] if row else None


async def set_emotional_state(user_id: int, state: str | None) -> None:
    """Met à jour l'état émotionnel."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET emotional_state = $1 WHERE id = $2",
            state, user_id
        )


async def get_last_message_time(user_id: int) -> datetime | None:
    """Récupère le timestamp du dernier message."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_message_at FROM users WHERE id = $1", user_id
        )
        return row["last_message_at"] if row else None


async def set_last_message_time(user_id: int) -> None:
    """Met à jour le timestamp du dernier message."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_message_at = NOW() WHERE id = $1",
            user_id
        )


# ============== V5: Psychology data functions ==============

async def get_inside_jokes(user_id: int) -> list:
    """Récupère les inside jokes d'un utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT inside_jokes FROM users WHERE id = $1", user_id
        )
        if row and row["inside_jokes"]:
            return safe_json_loads(row["inside_jokes"], [], f"inside_jokes user {user_id}")
        return []


async def update_inside_jokes(user_id: int, jokes: list) -> None:
    """Met à jour les inside jokes."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET inside_jokes = $1 WHERE id = $2",
            json.dumps(jokes, ensure_ascii=False, default=str),
            user_id
        )


async def get_pending_events(user_id: int) -> list:
    """Récupère les événements en attente."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT pending_events FROM users WHERE id = $1", user_id
        )
        if row and row["pending_events"]:
            return safe_json_loads(row["pending_events"], [], f"pending_events user {user_id}")
        return []


async def update_pending_events(user_id: int, events: list) -> None:
    """Met à jour les événements en attente."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET pending_events = $1 WHERE id = $2",
            json.dumps(events, ensure_ascii=False, default=str),
            user_id
        )


async def update_attachment_score(user_id: int, score: float) -> None:
    """Met à jour le score d'attachement."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET attachment_score = $1 WHERE id = $2",
            score, user_id
        )


async def increment_session_count(user_id: int) -> int:
    """Incrémente le compteur de sessions."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET session_count = session_count + 1
            WHERE id = $1
            RETURNING session_count
            """,
            user_id
        )
        return row["session_count"] if row else 0


async def increment_user_initiated(user_id: int) -> None:
    """Incrémente le compteur de conversations initiées par user."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET user_initiated_count = user_initiated_count + 1 WHERE id = $1",
            user_id
        )


async def increment_vulnerabilities(user_id: int) -> None:
    """Incrémente le compteur de vulnérabilités partagées."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET vulnerabilities_shared = vulnerabilities_shared + 1 WHERE id = $1",
            user_id
        )


async def get_psychology_data(user_id: int) -> dict:
    """Récupère toutes les données psychology pour un user."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                inside_jokes, pending_events, attachment_score,
                session_count, user_initiated_count, vulnerabilities_shared,
                total_messages, first_message_at, last_message_at
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {}

        return {
            "inside_jokes": safe_json_loads(row["inside_jokes"], [], "psych inside_jokes"),
            "pending_events": safe_json_loads(row["pending_events"], [], "psych pending_events"),
            "attachment_score": row["attachment_score"] or 0,
            "session_count": row["session_count"] or 0,
            "user_initiated_count": row["user_initiated_count"] or 0,
            "vulnerabilities_shared": row["vulnerabilities_shared"] or 0,
            "total_messages": row["total_messages"] or 0,
            "first_message_at": row["first_message_at"],
            "last_message_at": row["last_message_at"],
        }


# ============== V3: Momentum system functions ==============

async def init_momentum_columns() -> None:
    """Ajoute les colonnes momentum (appelé dans init_db)."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            momentum FLOAT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            intimacy_history INT DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            messages_since_climax INT DEFAULT 999
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS
            current_tier INT DEFAULT 1
        """)


async def get_momentum_state(user_id: int) -> dict:
    """Récupère l'état momentum pour un user."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT momentum, intimacy_history, messages_since_climax,
                   current_tier, messages_this_session, last_message_at
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "momentum": 0.0,
                "intimacy_history": 0,
                "messages_since_climax": 999,
                "current_tier": 1,
                "messages_this_session": 0,
                "last_message_at": None,
            }

        return {
            "momentum": float(row["momentum"] or 0),
            "intimacy_history": row["intimacy_history"] or 0,
            "messages_since_climax": row["messages_since_climax"] or 999,
            "current_tier": row["current_tier"] or 1,
            "messages_this_session": row["messages_this_session"] or 0,
            "last_message_at": row["last_message_at"],
        }


async def update_momentum_state(
    user_id: int,
    momentum: float,
    tier: int,
    messages_this_session: int,
    messages_since_climax: int | None = None
) -> None:
    """Met à jour l'état momentum."""
    async with get_pool().acquire() as conn:
        if messages_since_climax is not None:
            await conn.execute("""
                UPDATE users SET
                    momentum = $2,
                    current_tier = $3,
                    messages_this_session = $4,
                    messages_since_climax = $5
                WHERE id = $1
            """, user_id, momentum, tier, messages_this_session, messages_since_climax)
        else:
            await conn.execute("""
                UPDATE users SET
                    momentum = $2,
                    current_tier = $3,
                    messages_this_session = $4,
                    messages_since_climax = messages_since_climax + 1
                WHERE id = $1
            """, user_id, momentum, tier, messages_this_session)


async def start_climax_recovery(user_id: int, new_momentum: float) -> None:
    """Démarre la phase de recovery après climax."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                momentum = $2,
                messages_since_climax = 0,
                last_climax_at = NOW(),
                intimacy_history = intimacy_history + 1
            WHERE id = $1
        """, user_id, new_momentum)


async def reset_momentum(user_id: int) -> None:
    """Reset le momentum (pour /reset momentum)."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                momentum = 0,
                current_tier = 1,
                messages_since_climax = 999
            WHERE id = $1
        """, user_id)


async def reset_intimacy_history(user_id: int) -> None:
    """Reset l'historique d'intimité (pour /reset intimacy)."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                intimacy_history = 0
            WHERE id = $1
        """, user_id)


# ============== V8: Luna mood system functions ==============

async def get_mood_state(user_id: int) -> dict:
    """Récupère l'état du mood Luna pour un user."""
    # Map old mood values to new 8-state system
    MOOD_MIGRATION = {
        "normal": "neutral",
        "horny": "playful",  # HORNY replaced by PLAYFUL
    }

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT luna_mood, mood_updated_at, last_horny_at, last_climax_at
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "luna_mood": "neutral",
                "mood_updated_at": None,
                "last_horny_at": None,
                "last_climax_at": None,
            }

        raw_mood = row["luna_mood"] or "neutral"
        migrated_mood = MOOD_MIGRATION.get(raw_mood, raw_mood)

        return {
            "luna_mood": migrated_mood,
            "mood_updated_at": row["mood_updated_at"],
            "last_horny_at": row["last_horny_at"],
            "last_climax_at": row["last_climax_at"],
        }


async def update_luna_mood(user_id: int, mood: str) -> None:
    """Met à jour le mood de Luna."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                luna_mood = $2,
                mood_updated_at = NOW()
            WHERE id = $1
        """, user_id, mood)


# ============== TRUST SYSTEM (V7) ==============

async def get_trust_state(user_id: int) -> dict:
    """
    Récupère l'état de confiance d'un utilisateur.

    Returns:
        dict avec trust_score, luna_last_state, unlocked_secrets
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COALESCE(trust_score, 50) as trust_score,
                COALESCE(luna_last_state, 'neutral') as luna_last_state,
                COALESCE(unlocked_secrets, '[]'::jsonb) as unlocked_secrets,
                last_trust_update
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "trust_score": 50,
                "luna_last_state": "neutral",
                "unlocked_secrets": [],
                "last_trust_update": None
            }

        return {
            "trust_score": max(0, min(100, row["trust_score"] or 50)),  # Clamp 0-100
            "luna_last_state": row["luna_last_state"],
            "unlocked_secrets": safe_json_loads(row["unlocked_secrets"], [], "unlocked_secrets"),
            "last_trust_update": row["last_trust_update"]
        }


async def update_trust_score(user_id: int, new_score: int, luna_state: str = None) -> None:
    """
    Met à jour le score de confiance.

    Args:
        user_id: ID utilisateur
        new_score: Nouveau score (0-100)
        luna_state: État émotionnel de Luna (optionnel)
    """
    new_score = max(0, min(100, new_score))  # Clamp 0-100

    async with get_pool().acquire() as conn:
        if luna_state:
            await conn.execute("""
                UPDATE users SET
                    trust_score = $2,
                    luna_last_state = $3,
                    last_trust_update = NOW()
                WHERE id = $1
            """, user_id, new_score, luna_state)
        else:
            await conn.execute("""
                UPDATE users SET
                    trust_score = $2,
                    last_trust_update = NOW()
                WHERE id = $1
            """, user_id, new_score)


async def add_unlocked_secret(user_id: int, secret_id: str) -> None:
    """Ajoute un secret débloqué pour l'utilisateur."""
    async with get_pool().acquire() as conn:
        # Ajoute le secret s'il n'existe pas déjà
        await conn.execute("""
            UPDATE users SET
                unlocked_secrets = COALESCE(unlocked_secrets, '[]'::jsonb) || $2::jsonb
            WHERE id = $1
            AND NOT (COALESCE(unlocked_secrets, '[]'::jsonb) @> $2::jsonb)
        """, user_id, json.dumps([secret_id]))


async def get_unlocked_secrets(user_id: int) -> list:
    """Récupère la liste des secrets débloqués."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COALESCE(unlocked_secrets, '[]'::jsonb) as secrets
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return []

        return safe_json_loads(row["secrets"], [], f"unlocked_secrets user {user_id}")


# ============== PHASE A: Intent + AHA ==============

async def get_user_intent(user_id: int) -> str | None:
    """Récupère l'intent de l'utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_intent FROM users WHERE id = $1", user_id
        )
        return row["user_intent"] if row and row["user_intent"] else None


async def set_user_intent(user_id: int, intent: str) -> None:
    """Définit l'intent de l'utilisateur."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET user_intent = $1 WHERE id = $2",
            intent, user_id
        )


async def get_aha_triggered(user_id: int) -> bool:
    """Vérifie si le AHA moment a été déclenché."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT aha_triggered FROM users WHERE id = $1", user_id
        )
        return row["aha_triggered"] if row and row["aha_triggered"] else False


async def set_aha_triggered(user_id: int) -> None:
    """Marque le AHA moment comme déclenché."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET aha_triggered = TRUE WHERE id = $1", user_id
        )


# ============== PHASE B: Gates + Investment ==============

async def get_gates_triggered(user_id: int) -> list[str]:
    """Récupère la liste des gates déjà déclenchées."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT gates_triggered FROM users WHERE id = $1", user_id
        )
        if row and row["gates_triggered"]:
            return safe_json_loads(row["gates_triggered"], [], f"gates_triggered user {user_id}")
        return []


async def add_gate_triggered(user_id: int, gate_id: str) -> None:
    """Ajoute une gate déclenchée."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                gates_triggered = COALESCE(gates_triggered, '[]'::jsonb) || $2::jsonb
            WHERE id = $1
            AND NOT (COALESCE(gates_triggered, '[]'::jsonb) @> $2::jsonb)
        """, user_id, json.dumps([gate_id]))


async def get_investment_data(user_id: int) -> dict:
    """Récupère les données d'investissement."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COALESCE(investment_score, 0) as investment_score,
                COALESCE(secrets_shared_count, 0) as secrets_shared_count,
                COALESCE(compliments_given, 0) as compliments_given,
                COALESCE(questions_about_luna, 0) as questions_about_luna,
                COALESCE(user_segment, 'casual') as user_segment
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "investment_score": 0,
                "secrets_shared_count": 0,
                "compliments_given": 0,
                "questions_about_luna": 0,
                "user_segment": "casual"
            }

        return dict(row)


async def update_investment(
    user_id: int,
    score_delta: int = 0,
    secret: bool = False,
    compliment: bool = False,
    question_luna: bool = False
) -> None:
    """Met à jour les investissements utilisateur."""
    async with get_pool().acquire() as conn:
        # Utiliser une requête statique pour éviter l'injection SQL
        await conn.execute("""
            UPDATE users SET
                investment_score = investment_score + $2,
                secrets_shared_count = secrets_shared_count + $3,
                compliments_given = compliments_given + $4,
                questions_about_luna = questions_about_luna + $5
            WHERE id = $1
        """, user_id, score_delta,
             1 if secret else 0,
             1 if compliment else 0,
             1 if question_luna else 0)


async def update_user_segment(user_id: int, segment: str) -> None:
    """Met à jour le segment utilisateur."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET user_segment = $1 WHERE id = $2",
            segment, user_id
        )


# ============== PHASE C: Churn + Win-back ==============

async def get_churn_state(user_id: int) -> dict:
    """Récupère l'état de churn d'un utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COALESCE(churn_risk, 'low') as churn_risk,
                COALESCE(churn_score, 0) as churn_score,
                last_churn_check
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "churn_risk": "low",
                "churn_score": 0,
                "last_churn_check": None
            }

        return dict(row)


async def update_churn_state(user_id: int, risk: str, score: float) -> None:
    """Met à jour l'état de churn."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                churn_risk = $2,
                churn_score = $3,
                last_churn_check = NOW()
            WHERE id = $1
        """, user_id, risk, score)


async def get_winback_state(user_id: int) -> dict:
    """Récupère l'état win-back d'un utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                winback_stage,
                last_winback_at,
                COALESCE(winback_attempts, 0) as winback_attempts
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "winback_stage": None,
                "last_winback_at": None,
                "winback_attempts": 0
            }

        return dict(row)


async def update_winback_state(user_id: int, stage: str) -> None:
    """Met à jour l'état win-back après envoi."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                winback_stage = $2,
                last_winback_at = NOW(),
                winback_attempts = winback_attempts + 1
            WHERE id = $1
        """, user_id, stage)


async def reset_winback_state(user_id: int) -> None:
    """Reset le win-back quand l'utilisateur revient."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                winback_stage = NULL,
                winback_attempts = 0,
                churn_risk = 'low',
                churn_score = 0
            WHERE id = $1
        """, user_id)


async def get_timing_profile(user_id: int) -> dict:
    """Récupère le profil temporel d'un utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COALESCE(peak_hours, '[]'::jsonb) as peak_hours,
                COALESCE(active_days, '[]'::jsonb) as active_days,
                avg_response_time
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "peak_hours": [],
                "active_days": [],
                "avg_response_time": None
            }

        return {
            "peak_hours": safe_json_loads(row["peak_hours"], [], "peak_hours"),
            "active_days": safe_json_loads(row["active_days"], [], "active_days"),
            "avg_response_time": row["avg_response_time"]
        }


async def update_timing_profile(
    user_id: int,
    peak_hours: list[int],
    active_days: list[int],
    avg_response_time: float
) -> None:
    """Met à jour le profil temporel."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                peak_hours = $2,
                active_days = $3,
                avg_response_time = $4
            WHERE id = $1
        """, user_id, json.dumps(peak_hours), json.dumps(active_days), avg_response_time)


async def get_users_for_winback() -> list[dict]:
    """Récupère les utilisateurs éligibles au win-back."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id, telegram_id, memory, last_active,
                winback_stage, last_winback_at, winback_attempts
            FROM users
            WHERE last_active < NOW() - INTERVAL '7 days'
            AND (winback_stage IS NULL OR winback_stage != 'exhausted')
            AND subscription_status != 'active'
        """)
        return [dict(row) for row in rows]


async def get_users_at_churn_risk() -> list[dict]:
    """Récupère les utilisateurs à risque de churn."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id, telegram_id, memory, last_active,
                churn_risk, churn_score,
                total_messages, attachment_score
            FROM users
            WHERE last_active < NOW() - INTERVAL '24 hours'
            AND last_active > NOW() - INTERVAL '7 days'
            AND subscription_status != 'active'
        """)
        return [dict(row) for row in rows]


# ============== PHOTOS SYSTEM ==============

async def get_photo_state(user_id: int) -> dict:
    """Récupère l'état des photos pour un utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COALESCE(photos_sent, '[]'::jsonb) as photos_sent,
                last_photo_at,
                COALESCE(photos_count, 0) as photos_count
            FROM users WHERE id = $1
        """, user_id)

        if not row:
            return {
                "photos_sent": [],
                "last_photo_at": None,
                "photos_count": 0
            }

        return {
            "photos_sent": safe_json_loads(row["photos_sent"], [], "photos_sent"),
            "last_photo_at": row["last_photo_at"],
            "photos_count": row["photos_count"]
        }


async def log_photo_sent(user_id: int, photo_path: str, photo_type: str) -> None:
    """Enregistre l'envoi d'une photo."""
    async with get_pool().acquire() as conn:
        # Ajouter à la liste (garder les 50 dernières)
        await conn.execute("""
            UPDATE users SET
                photos_sent = (
                    SELECT jsonb_agg(elem)
                    FROM (
                        SELECT elem
                        FROM jsonb_array_elements(
                            COALESCE(photos_sent, '[]'::jsonb) || $2::jsonb
                        ) elem
                        ORDER BY elem->>'sent_at' DESC
                        LIMIT 50
                    ) sub
                ),
                last_photo_at = NOW(),
                photos_count = photos_count + 1
            WHERE id = $1
        """, user_id, json.dumps([{
            "path": photo_path,
            "type": photo_type,
            "sent_at": datetime.now(PARIS_TZ).isoformat()
        }]))


async def get_sent_photo_paths(user_id: int) -> list[str]:
    """Récupère la liste des chemins de photos déjà envoyées."""
    state = await get_photo_state(user_id)
    return [p.get("path", "") for p in state.get("photos_sent", [])]
