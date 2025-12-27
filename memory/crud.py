"""
Memory System - CRUD Operations

Toutes les opérations de base de données pour le système mémoire.
Utilise asyncpg directement (pas SQLAlchemy).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from .models import (
    UserFacts,
    RelationshipState,
    TimelineEvent,
    LunaState,
    EventType,
    TierThreshold,
)

logger = logging.getLogger(__name__)

# Pool global (injecté au démarrage)
_pool = None


def set_pool(pool):
    """Injecte le pool de connexions."""
    global _pool
    _pool = pool


def get_pool():
    """Récupère le pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call set_pool() first.")
    return _pool


# =============================================================================
# USERS
# =============================================================================

async def get_user(telegram_id: int) -> Optional[dict]:
    """Récupère un user par telegram_id."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM memory_users WHERE telegram_id = $1
        """, telegram_id)
        return dict(row) if row else None


async def get_user_by_id(user_id: UUID) -> Optional[dict]:
    """Récupère un user par UUID."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM memory_users WHERE id = $1
        """, user_id)
        return dict(row) if row else None


async def create_user(telegram_id: int) -> dict:
    """Crée un nouveau user."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO memory_users (telegram_id)
            VALUES ($1)
            ON CONFLICT (telegram_id) DO UPDATE SET telegram_id = $1
            RETURNING *
        """, telegram_id)

        user = dict(row)

        # Créer la relation associée
        await conn.execute("""
            INSERT INTO memory_relationships (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        """, user["id"])

        return user


async def get_or_create_user(telegram_id: int) -> dict:
    """Récupère ou crée un user."""
    user = await get_user(telegram_id)
    if user:
        return user
    return await create_user(telegram_id)


async def update_user(user_id: UUID, updates: dict) -> dict:
    """
    Met à jour les champs d'un user.

    Pour les champs JSONB (likes, secrets, etc.), merge au lieu de remplacer.
    """
    if not updates:
        return await get_user_by_id(user_id)

    async with get_pool().acquire() as conn:
        # Séparer les champs simples des JSONB arrays
        simple_fields = {}
        jsonb_appends = {}

        for key, value in updates.items():
            if key in ("likes", "dislikes", "secrets") and isinstance(value, list):
                jsonb_appends[key] = value
            elif key == "family" and isinstance(value, dict):
                # Merge family dict
                jsonb_appends[key] = value
            else:
                simple_fields[key] = value

        # Update simple fields
        if simple_fields:
            sets = []
            values = [user_id]
            for i, (k, v) in enumerate(simple_fields.items(), start=2):
                sets.append(f"{k} = ${i}")
                values.append(v)

            sets.append("updated_at = NOW()")

            await conn.execute(
                f"UPDATE memory_users SET {', '.join(sets)} WHERE id = $1",
                *values
            )

        # Append to JSONB arrays (sans doublons)
        for field, new_values in jsonb_appends.items():
            if field == "family":
                # Merge dict
                await conn.execute(f"""
                    UPDATE memory_users
                    SET {field} = {field} || $2::jsonb,
                        updated_at = NOW()
                    WHERE id = $1
                """, user_id, json.dumps(new_values))
            else:
                # Append to array (dedupe)
                for val in new_values:
                    await conn.execute(f"""
                        UPDATE memory_users
                        SET {field} = (
                            SELECT jsonb_agg(DISTINCT elem)
                            FROM jsonb_array_elements({field} || $2::jsonb) elem
                        ),
                        updated_at = NOW()
                        WHERE id = $1
                    """, user_id, json.dumps([val]))

        return await get_user_by_id(user_id)


async def update_user_state(user_id: UUID, state_updates: dict) -> None:
    """Met à jour l'état temps réel (luna_mood, current_topic, etc.)."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE memory_users
            SET state = state || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
        """, user_id, json.dumps(state_updates))


async def get_user_state(user_id: UUID) -> LunaState:
    """Récupère l'état temps réel."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT state FROM memory_users WHERE id = $1
        """, user_id)

        if row and row["state"]:
            return row["state"]

        return {"luna_mood": "neutral", "current_topic": None}


# =============================================================================
# RELATIONSHIPS
# =============================================================================

async def get_relationship(user_id: UUID) -> Optional[dict]:
    """Récupère la relation d'un user."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM memory_relationships WHERE user_id = $1
        """, user_id)
        return dict(row) if row else None


async def update_relationship(user_id: UUID, updates: dict) -> dict:
    """Met à jour la relation."""
    if not updates:
        return await get_relationship(user_id)

    async with get_pool().acquire() as conn:
        sets = []
        values = [user_id]

        for i, (k, v) in enumerate(updates.items(), start=2):
            if k in ("inside_jokes", "pet_names", "shared_memories"):
                # JSONB arrays - append
                sets.append(f"{k} = {k} || ${i}::jsonb")
                values.append(json.dumps([v] if isinstance(v, str) else v))
            else:
                sets.append(f"{k} = ${i}")
                values.append(v)

        sets.append("updated_at = NOW()")

        await conn.execute(
            f"UPDATE memory_relationships SET {', '.join(sets)} WHERE user_id = $1",
            *values
        )

        return await get_relationship(user_id)


async def increment_relationship(user_id: UUID, intimacy_delta: int = 0, trust_delta: int = 0) -> dict:
    """Incrémente intimacy/trust avec bounds check (1-10)."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships SET
                intimacy = LEAST(10, GREATEST(1, intimacy + $2)),
                trust = LEAST(10, GREATEST(1, trust + $3)),
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, intimacy_delta, trust_delta)

        return await get_relationship(user_id)


async def add_inside_joke(user_id: UUID, joke: str) -> None:
    """Ajoute un inside joke."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships SET
                inside_jokes = inside_jokes || $2::jsonb,
                updated_at = NOW()
            WHERE user_id = $1
            AND NOT (inside_jokes @> $2::jsonb)
        """, user_id, json.dumps([joke]))


async def increment_day(user_id: UUID) -> int:
    """Incrémente le jour de relation. Retourne le nouveau jour."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE memory_relationships SET
                day = day + 1,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING day
        """, user_id)
        return row["day"] if row else 1


# =============================================================================
# TIMELINE
# =============================================================================

async def add_event(
    user_id: UUID,
    event_type: str,
    summary: str,
    keywords: list[str],
    score: int = 7,
    pinned: bool = False,
    event_date: Optional[datetime] = None
) -> dict:
    """Ajoute un événement à la timeline."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO memory_timeline
                (user_id, type, summary, keywords, score, pinned, event_date)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, COALESCE($7, NOW()))
            RETURNING *
        """, user_id, event_type, summary, json.dumps(keywords), score, pinned, event_date)

        logger.info(f"Event added: [{event_type}] {summary[:50]}...")
        return dict(row)


async def get_hot_events(user_id: UUID, limit: int = 10) -> list[dict]:
    """Récupère les événements HOT (récents, < 7 jours)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1 AND tier = 'hot'
            ORDER BY event_date DESC
            LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]


async def get_pinned_events(user_id: UUID) -> list[dict]:
    """Récupère les événements épinglés (toujours inclus)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1 AND pinned = TRUE
            ORDER BY event_date DESC
        """, user_id)
        return [dict(r) for r in rows]


async def get_events_by_keywords(
    user_id: UUID,
    keywords: list[str],
    limit: int = 5
) -> list[dict]:
    """Recherche des événements par keywords."""
    if not keywords:
        return []

    async with get_pool().acquire() as conn:
        # Use ?| operator for JSONB array contains any of the keywords
        rows = await conn.fetch("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1 AND keywords ?| $2
            ORDER BY
                pinned DESC,
                CASE tier WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 ELSE 3 END,
                event_date DESC
            LIMIT $3
        """, user_id, keywords, limit)
        return [dict(r) for r in rows]


async def get_luna_said(user_id: UUID, topic: Optional[str] = None, limit: int = 5) -> list[dict]:
    """Récupère ce que Luna a dit (sur un topic ou en général)."""
    async with get_pool().acquire() as conn:
        if topic:
            rows = await conn.fetch("""
                SELECT * FROM memory_timeline
                WHERE user_id = $1
                AND type = 'luna_said'
                AND keywords @> $2::jsonb
                ORDER BY event_date DESC
                LIMIT $3
            """, user_id, json.dumps([topic]), limit)
        else:
            rows = await conn.fetch("""
                SELECT * FROM memory_timeline
                WHERE user_id = $1 AND type = 'luna_said'
                ORDER BY event_date DESC
                LIMIT $2
            """, user_id, limit)

        return [dict(r) for r in rows]


async def get_events_by_type(user_id: UUID, event_type: str, limit: int = 10) -> list[dict]:
    """Récupère les événements d'un type spécifique."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1 AND type = $2
            ORDER BY event_date DESC
            LIMIT $3
        """, user_id, event_type, limit)
        return [dict(r) for r in rows]


async def update_event(event_id: UUID, updates: dict) -> dict:
    """Met à jour un événement."""
    async with get_pool().acquire() as conn:
        sets = []
        values = [event_id]

        for i, (k, v) in enumerate(updates.items(), start=2):
            if k == "keywords":
                sets.append(f"{k} = ${i}::jsonb")
                values.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${i}")
                values.append(v)

        row = await conn.fetchrow(
            f"UPDATE memory_timeline SET {', '.join(sets)} WHERE id = $1 RETURNING *",
            *values
        )
        return dict(row) if row else None


async def find_similar_event(user_id: UUID, keywords: list[str], event_type: str) -> Optional[dict]:
    """Trouve un événement similaire (pour éviter doublons)."""
    if not keywords:
        return None

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1
            AND type = $2
            AND keywords ?| $3
            ORDER BY event_date DESC
            LIMIT 1
        """, user_id, event_type, keywords)
        return dict(row) if row else None


# =============================================================================
# MAINTENANCE (Cron jobs)
# =============================================================================

async def update_tiers() -> int:
    """
    Met à jour les tiers des événements:
    - hot → warm si > 7 jours
    - warm → cold si > 90 jours

    Retourne le nombre d'événements mis à jour.
    """
    now = datetime.now()
    hot_cutoff = now - timedelta(days=TierThreshold.HOT_DAYS)
    warm_cutoff = now - timedelta(days=TierThreshold.WARM_DAYS)

    async with get_pool().acquire() as conn:
        # hot → warm
        result1 = await conn.execute("""
            UPDATE memory_timeline SET tier = 'warm'
            WHERE tier = 'hot' AND event_date < $1 AND pinned = FALSE
        """, hot_cutoff)

        # warm → cold
        result2 = await conn.execute("""
            UPDATE memory_timeline SET tier = 'cold'
            WHERE tier = 'warm' AND event_date < $1 AND pinned = FALSE
        """, warm_cutoff)

        count1 = int(result1.split()[-1]) if result1 else 0
        count2 = int(result2.split()[-1]) if result2 else 0

        if count1 or count2:
            logger.info(f"Tier update: {count1} hot→warm, {count2} warm→cold")

        return count1 + count2


async def cleanup_old_cold_events(user_id: UUID, keep_count: int = 50) -> int:
    """
    Supprime les anciens événements cold (garde les keep_count plus récents).
    Ne supprime jamais les événements pinned.
    """
    async with get_pool().acquire() as conn:
        result = await conn.execute("""
            DELETE FROM memory_timeline
            WHERE id IN (
                SELECT id FROM memory_timeline
                WHERE user_id = $1 AND tier = 'cold' AND pinned = FALSE
                ORDER BY event_date DESC
                OFFSET $2
            )
        """, user_id, keep_count)

        count = int(result.split()[-1]) if result else 0
        if count:
            logger.info(f"Cleaned up {count} old cold events for user {user_id}")

        return count
