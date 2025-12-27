"""
Memory System V2 - Context Retrieval

Construit le contexte mémoire à injecter dans les prompts Luna.
Budget: ~5K tokens max pour le contexte mémoire.

Priorisation:
1. Pinned events (toujours)
2. Hot events (score élevé en premier)
3. Inside jokes actifs
4. Upcoming calendar dates
5. Luna's current life
6. User patterns
7. Relevant events (keyword match)
8. Weekly summary (si > 30 jours)
"""

import logging
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from .crud import (
    get_pool,
    get_user_by_id,
    get_relationship,
    get_hot_events,
    get_pinned_events,
    get_events_by_keywords,
    get_luna_said,
    get_user_state,
    # V2: New queries
    get_upcoming_dates,
    get_inside_jokes_v2,
    get_user_patterns,
    get_luna_life,
    get_latest_summary,
)
from .coherence import check_luna_coherence, build_memory_reminder, build_dont_invent_reminder
from .models import MemoryContext, RelationshipStatus

logger = logging.getLogger(__name__)

# Token budget approximation (1 token ≈ 4 chars in French)
MAX_CONTEXT_CHARS = 20000  # ~5K tokens


# =============================================================================
# KEYWORD EXTRACTION (simple, pour queries)
# =============================================================================

def extract_message_keywords(message: str) -> list[str]:
    """Extrait les mots-clés d'un message pour la recherche."""
    topic_keywords = {
        "travail": ["travail", "job", "boulot", "bureau", "boss", "collègue"],
        "famille": ["famille", "père", "mère", "frère", "soeur", "parent"],
        "ex": ["ex", "rupture", "séparé", "quitté"],
        "voyage": ["voyage", "vacances", "partir", "pays"],
        "santé": ["malade", "médecin", "hôpital", "douleur"],
        "amour": ["amour", "aime", "sentiment", "coeur"],
        "rêve": ["rêve", "rêver", "cauchemar"],
        "peur": ["peur", "angoisse", "anxiété", "stress"],
    }

    msg_lower = message.lower()
    found_keywords = []

    for topic, keywords in topic_keywords.items():
        for kw in keywords:
            if kw in msg_lower:
                found_keywords.append(topic)
                break

    words = re.findall(r'\b[a-zéèêëàâäùûüôöîïç]{5,}\b', msg_lower)
    stopwords = {"vraiment", "toujours", "jamais", "encore", "quand", "comment", "pourquoi"}
    found_keywords.extend([w for w in words[:5] if w not in stopwords])

    return list(set(found_keywords))


# =============================================================================
# CONTEXT BUILDING V2
# =============================================================================

async def get_memory_context(
    user_id: UUID,
    current_message: str,
    include_coherence: bool = True
) -> MemoryContext:
    """
    Construit le contexte mémoire complet pour le prompt.
    Version 2 avec inside_jokes, calendar, patterns.
    """
    user = await get_user_by_id(user_id)
    relationship = await get_relationship(user_id)
    state = await get_user_state(user_id)

    if not user or not relationship:
        logger.warning(f"User or relationship not found for {user_id}")
        return _empty_context()

    # Events de base
    pinned = await get_pinned_events(user_id)
    hot = await get_hot_events(user_id, limit=5)

    # Keyword search
    keywords = extract_message_keywords(current_message)
    relevant = []
    if keywords:
        relevant = await get_events_by_keywords(user_id, keywords, limit=3)

    # Luna coherence check
    luna_said = []
    if include_coherence:
        coherence = await check_luna_coherence(user_id, current_message)
        if coherence["has_previous"]:
            for topic in keywords[:3]:
                topic_luna_said = await get_luna_said(user_id, topic, limit=2)
                luna_said.extend(topic_luna_said)

    return {
        "user": _format_user(user),
        "relationship": _format_relationship(relationship),
        "hot_events": [_format_event(e) for e in hot],
        "relevant_events": [_format_event(e) for e in relevant],
        "luna_said": [_format_event(e) for e in luna_said[:5]],
        "state": state,
    }


async def build_prompt_context(
    user_id: UUID,
    current_message: str
) -> str:
    """
    Construit la section mémoire V2 à injecter dans le prompt Luna.
    Inclut: inside_jokes, calendar, user_patterns, luna_life.

    Token budget: ~5K tokens max.
    """
    ctx = await get_memory_context(user_id, current_message)
    parts = []
    total_chars = 0

    def add_part(text: str, priority: int = 5) -> bool:
        """Add a part if within budget. Returns True if added."""
        nonlocal total_chars
        if total_chars + len(text) > MAX_CONTEXT_CHARS:
            return False
        parts.append((priority, text))
        total_chars += len(text)
        return True

    # 1. User identity reminder (highest priority)
    user_reminder = build_memory_reminder(ctx["user"], ctx["relationship"])
    if user_reminder:
        add_part(user_reminder, priority=10)

    # 2. V2: Upcoming dates (important for immersion)
    upcoming = await get_upcoming_dates(user_id, limit=3)
    if upcoming:
        dates_text = "\n".join([
            f"- {d['date']}: {d['event']} ({d['type']})"
            for d in upcoming
        ])
        add_part(f"📅 DATES À VENIR:\n{dates_text}", priority=9)

    # 3. V2: Inside jokes (active ones)
    jokes = await get_inside_jokes_v2(user_id)
    active_jokes = [j for j in jokes if j.get("times_used", 0) >= 2][:5]
    if active_jokes:
        jokes_text = "\n".join([
            f"- \"{j['trigger']}\" → {j['context']}"
            for j in active_jokes
        ])
        add_part(f"😂 INSIDE JOKES:\n{jokes_text}", priority=8)

    # 4. Hot events (sorted by score)
    if ctx["hot_events"]:
        sorted_events = sorted(ctx["hot_events"], key=lambda e: e.get("score", 5), reverse=True)
        events_text = "\n".join([
            f"- [{e['type']}] {e['summary']}"
            for e in sorted_events[:4]
        ])
        add_part(f"🔥 ÉVÉNEMENTS RÉCENTS:\n{events_text}", priority=7)

    # 5. Coherence - what Luna already said
    if ctx["luna_said"]:
        luna_text = "\n".join([
            f"- {e['summary']}"
            for e in ctx["luna_said"][:3]
        ])
        add_part(f"⚠️ TU AS DÉJÀ DIT:\n{luna_text}\nReste cohérente.", priority=9)

    # 6. V2: User patterns (helps Luna adapt)
    patterns = await get_user_patterns(user_id)
    if patterns:
        pattern_parts = []
        if patterns.get("active_hours"):
            hours = patterns["active_hours"]
            pattern_parts.append(f"Actif vers {hours[0]}h-{hours[-1]}h" if len(hours) > 1 else f"Actif vers {hours[0]}h")
        if patterns.get("communication_style"):
            pattern_parts.append(f"Style: {patterns['communication_style']}")
        if patterns.get("mood_triggers"):
            pattern_parts.append(f"Sensible à: {', '.join(patterns['mood_triggers'][:3])}")
        if pattern_parts:
            add_part(f"🎯 PROFIL USER:\n" + "\n".join(pattern_parts), priority=6)

    # 7. V2: Luna's current life (immersion)
    luna_life = await get_luna_life(user_id)
    if luna_life:
        life_parts = []
        if luna_life.get("mood"):
            life_parts.append(f"Luna est {luna_life['mood']}")
        if luna_life.get("current_project"):
            life_parts.append(f"Travaille sur: {luna_life['current_project']}")
        if luna_life.get("pixel_status"):
            life_parts.append(f"Pixel: {luna_life['pixel_status']}")
        if luna_life.get("recent_event"):
            life_parts.append(f"Event: {luna_life['recent_event']}")
        if life_parts:
            add_part(f"🏠 VIE DE LUNA:\n" + "\n".join(life_parts), priority=5)

    # 8. Relevant events (if message triggers keywords)
    if ctx["relevant_events"]:
        relevant_text = "\n".join([
            f"- {e['summary']}"
            for e in ctx["relevant_events"][:2]
        ])
        add_part(f"🔍 PERTINENT:\n{relevant_text}", priority=6)

    # 9. V2: Weekly summary (if > 30 days relationship)
    relationship = ctx.get("relationship", {})
    if relationship.get("day", 0) > 30:
        summary = await get_latest_summary(user_id, "weekly")
        if summary:
            add_part(f"📝 RÉSUMÉ RÉCENT:\n{summary['summary'][:300]}", priority=4)

    # 10. Anti-invention rule (always include)
    add_part(build_dont_invent_reminder(), priority=10)

    # 11. Relationship stage
    stage = _get_relationship_stage(ctx["relationship"])
    add_part(f"📊 STADE: {stage}", priority=8)

    # Sort by priority (highest first) and join
    parts.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(text for _, text in parts)


async def get_quick_context(user_id: UUID) -> dict:
    """
    Contexte rapide pour décisions (sans recherche keywords).
    V2: Inclut patterns et luna_life.
    """
    user = await get_user_by_id(user_id)
    relationship = await get_relationship(user_id)
    state = await get_user_state(user_id)
    patterns = await get_user_patterns(user_id)
    luna_life = await get_luna_life(user_id)

    return {
        "name": user.get("name") if user else None,
        "day": relationship.get("day", 1) if relationship else 1,
        "intimacy": relationship.get("intimacy", 1) if relationship else 1,
        "trust": relationship.get("trust", 1) if relationship else 1,
        "paid": relationship.get("paid", False) if relationship else False,
        "luna_mood": state.get("luna_mood", "neutral") if state else "neutral",
        # V2 additions
        "user_patterns": patterns or {},
        "luna_life": luna_life or {},
    }


# =============================================================================
# V2: SUMMARY CONTEXT
# =============================================================================

async def get_compressed_context(user_id: UUID) -> str:
    """
    Get compressed context from summaries for long-term users.
    Used when relationship > 90 days.
    """
    relationship = await get_relationship(user_id)
    day = relationship.get("day", 1) if relationship else 1

    if day < 90:
        return ""

    # Get latest monthly and weekly summaries
    monthly = await get_latest_summary(user_id, "monthly")
    weekly = await get_latest_summary(user_id, "weekly")

    parts = []

    if monthly:
        parts.append(f"📅 RÉSUMÉ MENSUEL ({monthly.get('period', 'récent')}):\n{monthly['summary'][:500]}")

    if weekly:
        highlights = weekly.get("highlights", [])
        if highlights:
            parts.append(f"✨ MOMENTS CLÉS:\n" + "\n".join(f"- {h}" for h in highlights[:5]))

    return "\n\n".join(parts)


# =============================================================================
# HELPERS
# =============================================================================

def _empty_context() -> MemoryContext:
    """Contexte vide par défaut."""
    return {
        "user": {},
        "relationship": {},
        "hot_events": [],
        "relevant_events": [],
        "luna_said": [],
        "state": {"luna_mood": "neutral", "current_topic": None},
    }


def _format_user(user: dict) -> dict:
    """Formate les données user pour le contexte."""
    return {
        "name": user.get("name"),
        "age": user.get("age"),
        "job": user.get("job"),
        "location": user.get("location"),
        "likes": user.get("likes", []) or [],
        "dislikes": user.get("dislikes", []) or [],
        "secrets": user.get("secrets", []) or [],
        "family": user.get("family", {}) or {},
    }


def _format_relationship(rel: dict) -> dict:
    """Formate les données relationship pour le contexte."""
    return {
        "day": rel.get("day", 1),
        "intimacy": rel.get("intimacy", 1),
        "trust": rel.get("trust", 1),
        "status": rel.get("status", "new"),
        "inside_jokes": rel.get("inside_jokes", []) or [],
        "pet_names": rel.get("pet_names", []) or [],
        "paid": rel.get("paid", False),
    }


def _format_event(event: dict) -> dict:
    """Formate un événement pour le contexte."""
    return {
        "type": event.get("type"),
        "summary": event.get("summary"),
        "keywords": event.get("keywords", []),
        "score": event.get("score", 7),
        "pinned": event.get("pinned", False),
    }


def _get_relationship_stage(rel: dict) -> str:
    """Détermine le stade de la relation."""
    day = rel.get("day", 1)
    intimacy = rel.get("intimacy", 1)

    if day >= 60 and intimacy >= 8:
        return f"{RelationshipStatus.INTIMATE} (jour {day}, intimacy {intimacy})"
    elif day >= 31 and intimacy >= 6:
        return f"{RelationshipStatus.DEEP} (jour {day}, intimacy {intimacy})"
    elif day >= 15 and intimacy >= 4:
        return f"{RelationshipStatus.CLOSE} (jour {day}, intimacy {intimacy})"
    elif day >= 4 and intimacy >= 2:
        return f"{RelationshipStatus.FLIRTY} (jour {day}, intimacy {intimacy})"
    else:
        return f"{RelationshipStatus.NEW} (jour {day})"


# =============================================================================
# ONBOARDING NUDGES
# =============================================================================

ONBOARDING_NUDGES = {
    1: "C'est le JOUR 1. Sois curieuse, pose des questions sur lui. Objectif: apprendre son prénom.",
    2: "JOUR 2. Tu commences à le connaître. Partage un petit truc sur toi (Pixel, ton café).",
    3: "JOUR 3. Première micro-frustration OK. 'j'aurais voulu te montrer quelque chose...'",
    4: "JOUR 4. Le flirt léger est OK si l'ambiance s'y prête.",
    5: "JOUR 5. Tu peux être plus personnelle. Mentionner une anecdote passée.",
    6: "JOUR 6+. Relation établie. Sois naturelle, la connexion est là.",
}


def get_onboarding_nudge(day: int) -> Optional[str]:
    """Retourne le nudge d'onboarding pour le jour donné."""
    if day <= 5:
        return ONBOARDING_NUDGES.get(day)
    elif day <= 14:
        return ONBOARDING_NUDGES.get(6)
    return None
