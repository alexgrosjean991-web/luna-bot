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


# =============================================================================
# SUMMARIES (Weekly/Monthly)
# =============================================================================

async def add_summary(
    user_id: UUID,
    summary_type: str,  # 'weekly' or 'monthly'
    period: str,  # '2025-W03' or '2025-01'
    summary: str,
    highlights: list[str] = None,
    archived_data: dict = None
) -> dict:
    """Ajoute un résumé hebdo ou mensuel."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO memory_summaries
                (user_id, type, period, summary, highlights, archived_data)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            ON CONFLICT (user_id, period) DO UPDATE SET
                summary = EXCLUDED.summary,
                highlights = EXCLUDED.highlights,
                archived_data = EXCLUDED.archived_data
            RETURNING *
        """, user_id, summary_type, period,
             summary, json.dumps(highlights or []), json.dumps(archived_data or {}))

        logger.info(f"Summary added: [{summary_type}] {period}")
        return dict(row) if row else None


async def get_summaries(
    user_id: UUID,
    summary_type: str = None,
    limit: int = 12
) -> list[dict]:
    """Récupère les résumés d'un user."""
    async with get_pool().acquire() as conn:
        if summary_type:
            rows = await conn.fetch("""
                SELECT * FROM memory_summaries
                WHERE user_id = $1 AND type = $2
                ORDER BY created_at DESC
                LIMIT $3
            """, user_id, summary_type, limit)
        else:
            rows = await conn.fetch("""
                SELECT * FROM memory_summaries
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)

        return [dict(r) for r in rows]


async def get_latest_summary(user_id: UUID, summary_type: str) -> Optional[dict]:
    """Récupère le dernier résumé d'un type."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM memory_summaries
            WHERE user_id = $1 AND type = $2
            ORDER BY created_at DESC
            LIMIT 1
        """, user_id, summary_type)

        return dict(row) if row else None


# =============================================================================
# CALENDAR DATES
# =============================================================================

async def add_calendar_date(
    user_id: UUID,
    date: str,
    event: str,
    event_type: str,
    importance: int = 7
) -> None:
    """Ajoute une date au calendrier."""
    async with get_pool().acquire() as conn:
        new_date = {
            "date": date,
            "event": event,
            "type": event_type,
            "importance": importance
        }

        await conn.execute("""
            UPDATE memory_users
            SET calendar_dates = (
                SELECT jsonb_agg(elem)
                FROM (
                    SELECT elem FROM jsonb_array_elements(calendar_dates) elem
                    WHERE elem->>'date' != $2
                    UNION ALL
                    SELECT $3::jsonb
                ) sub
            ),
            updated_at = NOW()
            WHERE id = $1
        """, user_id, date, json.dumps(new_date))


async def get_upcoming_dates(user_id: UUID, days_ahead: int = 7, limit: int = 10) -> list[dict]:
    """Récupère les dates dans les N prochains jours."""
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT calendar_dates FROM memory_users WHERE id = $1
        """, user_id)

        if not row or not row["calendar_dates"]:
            return []

        dates = row["calendar_dates"]
        if isinstance(dates, str):
            dates = json.loads(dates)

        upcoming = [d for d in dates if today <= d.get("date", "") <= future]
        # Sort by date and limit
        upcoming.sort(key=lambda d: d.get("date", ""))
        return upcoming[:limit]


async def cleanup_past_dates(user_id: UUID) -> int:
    """Supprime les dates passées."""
    today = datetime.now().strftime("%Y-%m-%d")

    async with get_pool().acquire() as conn:
        result = await conn.execute("""
            UPDATE memory_users
            SET calendar_dates = (
                SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
                FROM jsonb_array_elements(calendar_dates) elem
                WHERE elem->>'date' >= $2
            ),
            updated_at = NOW()
            WHERE id = $1
        """, user_id, today)

        return 1 if result else 0


# =============================================================================
# LUNA LIFE
# =============================================================================

async def update_luna_life(user_id: UUID, updates: dict) -> None:
    """Met à jour la vie de Luna."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE memory_users
            SET luna_current_life = luna_current_life || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
        """, user_id, json.dumps(updates))


async def get_luna_life(user_id: UUID) -> dict:
    """Récupère la vie actuelle de Luna."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT luna_current_life FROM memory_users WHERE id = $1
        """, user_id)

        if row and row["luna_current_life"]:
            life = row["luna_current_life"]
            if isinstance(life, str):
                return json.loads(life)
            return life
        return {}


# =============================================================================
# USER PATTERNS
# =============================================================================

async def update_user_patterns(user_id: UUID, pattern_type: str, value) -> None:
    """Met à jour un pattern utilisateur."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE memory_users
            SET user_patterns = jsonb_set(
                COALESCE(user_patterns, '{}'),
                $2::text[],
                $3::jsonb
            ),
            updated_at = NOW()
            WHERE id = $1
        """, user_id, [pattern_type], json.dumps(value))


async def get_user_patterns(user_id: UUID) -> dict:
    """Récupère les patterns utilisateur."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_patterns FROM memory_users WHERE id = $1
        """, user_id)

        if row and row["user_patterns"]:
            patterns = row["user_patterns"]
            if isinstance(patterns, str):
                return json.loads(patterns)
            return patterns
        return {}


# =============================================================================
# INSIDE JOKES (Enhanced)
# =============================================================================

async def add_inside_joke_v2(
    user_id: UUID,
    trigger: str,
    context: str,
    importance: int = 6
) -> None:
    """Ajoute un inside joke avec tracking."""
    now = datetime.now().isoformat()

    async with get_pool().acquire() as conn:
        # Check if joke exists
        rel = await conn.fetchrow("""
            SELECT inside_jokes FROM memory_relationships WHERE user_id = $1
        """, user_id)

        jokes = rel["inside_jokes"] if rel and rel["inside_jokes"] else []
        if isinstance(jokes, str):
            jokes = json.loads(jokes)

        # Find existing joke by trigger
        existing_idx = next(
            (i for i, j in enumerate(jokes)
             if isinstance(j, dict) and j.get("trigger", "").lower() == trigger.lower()),
            None
        )

        if existing_idx is not None:
            # Update existing
            jokes[existing_idx]["times_used"] = jokes[existing_idx].get("times_used", 0) + 1
            jokes[existing_idx]["last_used"] = now
        else:
            # Add new
            jokes.append({
                "trigger": trigger,
                "context": context,
                "importance": importance,
                "times_used": 1,
                "last_used": now,
                "created_at": now
            })

        # Sort by usage and keep top 15
        jokes = sorted(
            [j for j in jokes if isinstance(j, dict)],
            key=lambda x: (x.get("times_used", 0) * 2 + x.get("importance", 0)),
            reverse=True
        )[:15]

        await conn.execute("""
            UPDATE memory_relationships
            SET inside_jokes = $2::jsonb,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, json.dumps(jokes))


async def get_inside_jokes_v2(user_id: UUID, limit: int = 10) -> list[dict]:
    """Récupère les inside jokes triés par usage."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            SELECT inside_jokes FROM memory_relationships WHERE user_id = $1
        """, user_id)

        if not row or not row["inside_jokes"]:
            return []

        jokes = row["inside_jokes"]
        if isinstance(jokes, str):
            jokes = json.loads(jokes)

        # Filter valid jokes and sort
        valid_jokes = [j for j in jokes if isinstance(j, dict) and j.get("trigger")]
        return sorted(
            valid_jokes,
            key=lambda x: (x.get("times_used", 0) * 2 + x.get("importance", 0)),
            reverse=True
        )[:limit]


# =============================================================================
# BULK OPERATIONS
# =============================================================================

async def get_all_active_users(days_inactive: int = 30) -> list[dict]:
    """Récupère tous les users actifs récemment."""
    cutoff = datetime.now() - timedelta(days=days_inactive)

    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.*, r.day, r.paid
            FROM memory_users u
            JOIN memory_relationships r ON r.user_id = u.id
            WHERE u.updated_at > $1
        """, cutoff)

        return [dict(r) for r in rows]
