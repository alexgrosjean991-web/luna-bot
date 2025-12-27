"""
Memory System - Context Retrieval

Construit le contexte mémoire à injecter dans les prompts Luna.
Priorise: pinned > hot > relevant keywords > warm
"""

import logging
import re
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
)
from .coherence import check_luna_coherence, build_memory_reminder, build_dont_invent_reminder
from .models import MemoryContext, RelationshipStatus

logger = logging.getLogger(__name__)


# =============================================================================
# KEYWORD EXTRACTION (simple, pour queries)
# =============================================================================

def extract_message_keywords(message: str) -> list[str]:
    """Extrait les mots-clés d'un message pour la recherche."""
    # Topics importants
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

    # Ajouter les mots significatifs (> 5 chars)
    words = re.findall(r'\b[a-zéèêëàâäùûüôöîïç]{5,}\b', msg_lower)
    stopwords = {"vraiment", "toujours", "jamais", "encore", "quand", "comment", "pourquoi"}
    found_keywords.extend([w for w in words[:5] if w not in stopwords])

    return list(set(found_keywords))


# =============================================================================
# CONTEXT BUILDING
# =============================================================================

async def get_memory_context(
    user_id: UUID,
    current_message: str,
    include_coherence: bool = True
) -> MemoryContext:
    """
    Construit le contexte mémoire complet pour le prompt.

    Args:
        user_id: UUID de l'utilisateur
        current_message: Message actuel de l'user
        include_coherence: Inclure le check de cohérence

    Returns:
        MemoryContext avec tous les éléments
    """
    # Récupérer les données de base
    user = await get_user_by_id(user_id)
    relationship = await get_relationship(user_id)
    state = await get_user_state(user_id)

    if not user or not relationship:
        logger.warning(f"User or relationship not found for {user_id}")
        return _empty_context()

    # Récupérer les événements
    pinned = await get_pinned_events(user_id)
    hot = await get_hot_events(user_id, limit=5)

    # Recherche par keywords du message actuel
    keywords = extract_message_keywords(current_message)
    relevant = []
    if keywords:
        relevant = await get_events_by_keywords(user_id, keywords, limit=3)

    # Ce que Luna a dit sur les topics mentionnés
    luna_said = []
    if include_coherence:
        coherence = await check_luna_coherence(user_id, current_message)
        if coherence["has_previous"]:
            # Récupérer les événements luna_said correspondants
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
    Construit la section mémoire à injecter dans le prompt Luna.

    Returns:
        String formaté à ajouter au prompt système
    """
    ctx = await get_memory_context(user_id, current_message)

    parts = []

    # 1. Memory reminder (qui est l'user)
    user_reminder = build_memory_reminder(ctx["user"], ctx["relationship"])
    if user_reminder:
        parts.append(user_reminder)

    # 2. Événements récents (hot)
    if ctx["hot_events"]:
        events_text = "\n".join([
            f"- [{e['type']}] {e['summary']}"
            for e in ctx["hot_events"][:3]
        ])
        parts.append(f"📅 ÉVÉNEMENTS RÉCENTS:\n{events_text}")

    # 3. Événements pertinents au message
    if ctx["relevant_events"]:
        relevant_text = "\n".join([
            f"- {e['summary']}"
            for e in ctx["relevant_events"][:2]
        ])
        parts.append(f"🔍 PERTINENT À CE MESSAGE:\n{relevant_text}")

    # 4. Cohérence - ce que Luna a déjà dit
    if ctx["luna_said"]:
        luna_text = "\n".join([
            f"- {e['summary']}"
            for e in ctx["luna_said"][:3]
        ])
        parts.append(f"⚠️ TU AS DÉJÀ DIT:\n{luna_text}\nReste cohérente avec ces déclarations.")

    # 5. Règle anti-invention
    parts.append(build_dont_invent_reminder())

    # 6. Relationship stage
    stage = _get_relationship_stage(ctx["relationship"])
    parts.append(f"📊 STADE RELATION: {stage}")

    return "\n\n".join(parts)


async def get_quick_context(user_id: UUID) -> dict:
    """
    Contexte rapide pour décisions (sans recherche keywords).
    Utilisé pour le routing LLM, modifiers, etc.
    """
    user = await get_user_by_id(user_id)
    relationship = await get_relationship(user_id)
    state = await get_user_state(user_id)

    return {
        "name": user.get("name") if user else None,
        "day": relationship.get("day", 1) if relationship else 1,
        "intimacy": relationship.get("intimacy", 1) if relationship else 1,
        "trust": relationship.get("trust", 1) if relationship else 1,
        "paid": relationship.get("paid", False) if relationship else False,
        "luna_mood": state.get("luna_mood", "neutral") if state else "neutral",
    }


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
    return None  # Plus de nudge après jour 14
