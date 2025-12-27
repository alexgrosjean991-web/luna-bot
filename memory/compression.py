"""
Memory System V2 - Compression Jobs

Crons pour maintenir la mémoire compacte sur 1 an:
- Weekly (Dimanche 3h): hot→warm, générer weekly summary
- Monthly (1er du mois 4h): warm→cold, archiver cold >1 an, générer monthly summary

Philosophy: "CODE = STUPIDE mais ROBUSTE, LLM = INTELLIGENT"
Le code fait la plomberie, le LLM résume intelligemment.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx

from .crud import (
    get_pool,
    get_all_active_users,
    get_hot_events,
    get_events_by_type,
    update_tiers,
    cleanup_old_cold_events,
    add_summary,
    get_summaries,
    get_inside_jokes_v2,
    get_user_by_id,
    get_relationship,
)

logger = logging.getLogger(__name__)

# Config
OPENROUTER_API_KEY = None  # Injecté au démarrage
HAIKU_MODEL = "anthropic/claude-3-haiku"


def set_api_key(key: str):
    """Injecte la clé API."""
    global OPENROUTER_API_KEY
    OPENROUTER_API_KEY = key


# =============================================================================
# WEEKLY COMPRESSION (Dimanche 3h)
# =============================================================================

async def run_weekly_compression() -> dict:
    """
    Job hebdomadaire:
    1. Update tiers (hot→warm pour events > 7 jours)
    2. Generate weekly summary for each active user
    3. Archive inactive inside jokes

    Returns:
        {"users_processed": int, "summaries_created": int, "tiers_updated": int}
    """
    stats = {
        "users_processed": 0,
        "summaries_created": 0,
        "tiers_updated": 0,
    }

    try:
        users = await get_all_active_users()
        logger.info(f"Weekly compression: processing {len(users)} active users")

        for user in users:
            user_id = user["id"]

            # 1. Update tiers
            updated = await update_tiers(user_id)
            stats["tiers_updated"] += updated

            # 2. Generate weekly summary
            summary = await _generate_weekly_summary(user_id)
            if summary:
                # Get current week identifier
                now = datetime.now()
                week_id = now.strftime("%Y-W%W")

                await add_summary(
                    user_id=user_id,
                    summary_type="weekly",
                    period=week_id,
                    summary=summary["summary"],
                    highlights=summary["highlights"]
                )
                stats["summaries_created"] += 1

            stats["users_processed"] += 1

        logger.info(f"Weekly compression complete: {stats}")

    except Exception as e:
        logger.error(f"Weekly compression error: {e}", exc_info=True)

    return stats


async def _generate_weekly_summary(user_id: UUID) -> Optional[dict]:
    """
    Generate weekly summary using LLM.
    Returns {"summary": str, "highlights": list[str]}
    """
    if not OPENROUTER_API_KEY:
        logger.warning("API key not set for compression")
        return None

    # Get hot events (last 7 days)
    events = await get_hot_events(user_id, limit=20)

    if len(events) < 3:
        # Not enough content for summary
        return None

    # Get user and relationship for context
    user = await get_user_by_id(user_id)
    relationship = await get_relationship(user_id)

    user_name = user.get("name", "l'utilisateur") if user else "l'utilisateur"
    day = relationship.get("day", 1) if relationship else 1

    # Format events for LLM
    events_text = "\n".join([
        f"- [{e.get('type')}] {e.get('summary')}"
        for e in events
    ])

    prompt = f"""Résume la semaine de conversation entre Luna et {user_name}.

ÉVÉNEMENTS DE LA SEMAINE:
{events_text}

CONTEXTE: Jour {day} de la relation.

Génère un JSON:
{{
    "summary": "Résumé de la semaine en 2-3 phrases (ce qui s'est passé, évolution de la relation)",
    "highlights": ["moment clé 1", "moment clé 2", "moment clé 3"]
}}

Règles:
- Focus sur les moments ÉMOTIONNELS importants
- Ignore les détails triviaux
- Max 3 highlights
- Le résumé doit aider Luna à se souvenir du contexte
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HAIKU_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 400,
                    "temperature": 0.3,
                }
            )

            data = response.json()

            if "choices" not in data:
                logger.warning(f"OpenRouter error: {data.get('error', data)}")
                return None

            content = data["choices"][0]["message"]["content"]

            # Parse JSON
            result = _safe_parse_json(content)
            if result and "summary" in result:
                return result

    except Exception as e:
        logger.error(f"Weekly summary generation error: {e}")

    return None


# =============================================================================
# MONTHLY COMPRESSION (1er du mois 4h)
# =============================================================================

async def run_monthly_compression() -> dict:
    """
    Job mensuel:
    1. Update tiers (warm→cold pour events > 90 jours)
    2. Archive cold events > 1 an
    3. Generate monthly summary
    4. Archive inactive inside jokes

    Returns:
        {"users_processed": int, "summaries_created": int, "events_archived": int}
    """
    stats = {
        "users_processed": 0,
        "summaries_created": 0,
        "events_archived": 0,
    }

    try:
        users = await get_all_active_users()
        logger.info(f"Monthly compression: processing {len(users)} active users")

        for user in users:
            user_id = user["id"]

            # 1. Update tiers
            await update_tiers(user_id)

            # 2. Archive old cold events
            archived = await cleanup_old_cold_events(user_id, days=365)
            stats["events_archived"] += archived

            # 3. Generate monthly summary
            summary = await _generate_monthly_summary(user_id)
            if summary:
                now = datetime.now()
                month_id = now.strftime("%Y-%m")

                await add_summary(
                    user_id=user_id,
                    summary_type="monthly",
                    period=month_id,
                    summary=summary["summary"],
                    highlights=summary["highlights"],
                    archived_data=summary.get("archived_data", {})
                )
                stats["summaries_created"] += 1

            stats["users_processed"] += 1

        logger.info(f"Monthly compression complete: {stats}")

    except Exception as e:
        logger.error(f"Monthly compression error: {e}", exc_info=True)

    return stats


async def _generate_monthly_summary(user_id: UUID) -> Optional[dict]:
    """
    Generate monthly summary using LLM.
    Includes archived data for cold events.
    """
    if not OPENROUTER_API_KEY:
        return None

    # Get weekly summaries from this month
    summaries = await get_summaries(user_id, "weekly", limit=4)

    # Get milestones
    milestones = await get_events_by_type(user_id, "milestone", limit=5)

    # Get conflicts
    conflicts = await get_events_by_type(user_id, "conflict", limit=3)

    if not summaries and not milestones:
        return None

    # Get inactive inside jokes for archival
    jokes = await get_inside_jokes_v2(user_id)
    inactive_jokes = [
        j for j in jokes
        if j.get("times_used", 0) < 2 or _is_stale(j.get("last_used"))
    ]

    # User context
    user = await get_user_by_id(user_id)
    user_name = user.get("name", "l'utilisateur") if user else "l'utilisateur"

    # Format content
    summaries_text = "\n".join([
        f"- Semaine {s['period']}: {s['summary']}"
        for s in summaries
    ]) if summaries else "(pas de résumés hebdo)"

    milestones_text = "\n".join([
        f"- {m['summary']}"
        for m in milestones
    ]) if milestones else "(pas de milestones)"

    conflicts_text = "\n".join([
        f"- {c['summary']}"
        for c in conflicts
    ]) if conflicts else "(pas de conflits)"

    prompt = f"""Résume le mois de relation entre Luna et {user_name}.

RÉSUMÉS HEBDOMADAIRES:
{summaries_text}

MILESTONES:
{milestones_text}

CONFLITS/TENSIONS:
{conflicts_text}

Génère un JSON:
{{
    "summary": "Résumé du mois en 3-4 phrases (évolution majeure de la relation)",
    "highlights": ["moment clé 1", "moment clé 2", "moment clé 3"]
}}

Règles:
- Focus sur l'ÉVOLUTION de la relation
- Note les changements de dynamique
- Identifie les patterns (positifs ou négatifs)
- Max 3 highlights
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HAIKU_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.3,
                }
            )

            data = response.json()

            if "choices" not in data:
                return None

            content = data["choices"][0]["message"]["content"]
            result = _safe_parse_json(content)

            if result and "summary" in result:
                # Add archived data
                result["archived_data"] = {
                    "inactive_jokes": inactive_jokes[:10],
                    "archived_at": datetime.now().isoformat()
                }
                return result

    except Exception as e:
        logger.error(f"Monthly summary generation error: {e}")

    return None


# =============================================================================
# HELPERS
# =============================================================================

def _safe_parse_json(content: str) -> Optional[dict]:
    """Parse JSON robustement."""
    import re

    if not content:
        return None

    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)

    start = content.find('{')
    if start == -1:
        return None

    brace_count = 0
    end = start
    for i, char in enumerate(content[start:], start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

    if brace_count != 0:
        return None

    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


def _is_stale(last_used: Optional[str], days: int = 30) -> bool:
    """Check if a timestamp is older than X days."""
    if not last_used:
        return True

    try:
        last = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
        return (datetime.now(last.tzinfo) - last).days > days
    except (ValueError, TypeError):
        return True


# =============================================================================
# INTEGRATION WITH BOT
# =============================================================================

async def schedule_compression_jobs(app) -> None:
    """
    Schedule compression jobs with APScheduler or similar.
    To be called from bot startup.

    Example with python-telegram-bot's JobQueue:
        schedule_compression_jobs(application)
    """
    from telegram.ext import Application

    if isinstance(app, Application):
        job_queue = app.job_queue

        # Weekly: Dimanche 3h Paris time
        job_queue.run_weekly(
            callback=_weekly_job_wrapper,
            day=6,  # Sunday
            time=datetime.strptime("03:00", "%H:%M").time(),
            name="weekly_compression"
        )

        # Monthly: 1er du mois 4h
        job_queue.run_monthly(
            callback=_monthly_job_wrapper,
            when=datetime.strptime("04:00", "%H:%M").time(),
            day=1,
            name="monthly_compression"
        )

        logger.info("Compression jobs scheduled")


async def _weekly_job_wrapper(context) -> None:
    """Wrapper for JobQueue compatibility."""
    await run_weekly_compression()


async def _monthly_job_wrapper(context) -> None:
    """Wrapper for JobQueue compatibility."""
    await run_monthly_compression()
