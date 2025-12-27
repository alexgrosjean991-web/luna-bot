"""
Memory System - Coherence Service

Vérifie la cohérence AVANT que Luna réponde:
1. Ce que Luna a déjà dit sur un sujet
2. Contradictions dans les faits user
3. Injection de contexte pour éviter les incohérences
"""

import json
import logging
from typing import Optional
from uuid import UUID

from .crud import get_pool, get_luna_said, find_similar_event, get_user_by_id

logger = logging.getLogger(__name__)


# Topics sensibles sur lesquels Luna doit être cohérente
LUNA_SENSITIVE_TOPICS = [
    "age", "travail", "job", "paris", "ville", "famille", "parents",
    "ex", "relation", "pixel", "chat", "rêve", "voyage", "peur",
    "secret", "passé", "enfance", "père", "mère"
]

# Catégories de faits user (pour détecter les updates vs contradictions)
FACT_CATEGORIES = {
    "identity": ["nom", "name", "prénom", "âge", "age"],
    "work": ["travail", "job", "boulot", "métier", "entreprise", "boîte"],
    "location": ["habite", "ville", "pays", "quartier", "région"],
    "relationship": ["célibataire", "couple", "marié", "copine", "femme", "ex"],
    "family": ["frère", "sœur", "parent", "père", "mère", "enfant", "fils", "fille"],
}


async def check_luna_coherence(user_id: UUID, message: str) -> dict:
    """
    Avant que Luna parle d'un sujet personnel, vérifie ce qu'elle a déjà dit.

    Args:
        user_id: ID de l'utilisateur
        message: Message de l'user (pour détecter le topic)

    Returns:
        {
            "has_previous": bool,
            "previous_statements": List[str],
            "prompt_injection": str  # À injecter dans le prompt
        }
    """
    msg_lower = message.lower()

    # Détecter si le message touche un topic sensible
    detected_topics = []
    for topic in LUNA_SENSITIVE_TOPICS:
        if topic in msg_lower:
            detected_topics.append(topic)

    if not detected_topics:
        return {
            "has_previous": False,
            "previous_statements": [],
            "prompt_injection": ""
        }

    # Query ce que Luna a déjà dit sur ces topics
    previous_statements = []

    for topic in detected_topics:
        luna_said = await get_luna_said(user_id, topic, limit=2)
        for event in luna_said:
            previous_statements.append(event["summary"])

    if previous_statements:
        # Construire l'injection pour le prompt
        statements_text = "\n- ".join(previous_statements[:3])
        prompt_injection = f"""
⚠️ COHÉRENCE REQUISE - Tu as déjà dit:
- {statements_text}

RÈGLE: Reste cohérente avec ces déclarations. Ne te contredis pas.
Si tu dois nuancer, fais-le naturellement ("enfin, c'est plus compliqué que ça...").
"""
        logger.info(f"Coherence check: found {len(previous_statements)} previous statements")

        return {
            "has_previous": True,
            "previous_statements": previous_statements[:3],
            "prompt_injection": prompt_injection.strip()
        }

    return {
        "has_previous": False,
        "previous_statements": [],
        "prompt_injection": ""
    }


def detect_fact_category(keywords: list[str]) -> Optional[str]:
    """Détecte la catégorie d'un fait basé sur ses keywords."""
    for category, category_keywords in FACT_CATEGORIES.items():
        for kw in keywords:
            if any(ck in kw.lower() for ck in category_keywords):
                return category
    return None


async def check_user_contradiction(
    user_id: UUID,
    new_summary: str,
    new_keywords: list[str]
) -> dict:
    """
    Avant de stocker un fait user, vérifie s'il contredit un fait existant.

    Returns:
        {
            "is_contradiction": bool,
            "is_update": bool,
            "existing_fact": str or None,
            "action": "store" | "update" | "flag"
        }
    """
    # Chercher un événement similaire
    existing = await find_similar_event(user_id, new_keywords, "moment")

    if not existing:
        return {
            "is_contradiction": False,
            "is_update": False,
            "existing_fact": None,
            "action": "store"
        }

    # Même catégorie = probablement une update
    existing_category = detect_fact_category(existing.get("keywords", []))
    new_category = detect_fact_category(new_keywords)

    if existing_category and new_category and existing_category == new_category:
        # Même catégorie (job, location, etc.) = UPDATE
        logger.info(f"Fact update detected: {existing_category}")
        return {
            "is_contradiction": False,
            "is_update": True,
            "existing_fact": existing["summary"],
            "action": "update"
        }

    # Catégories différentes ou non détectées = potentielle contradiction
    # On flag pour review plutôt que de bloquer
    logger.warning(f"Potential contradiction: '{existing['summary']}' vs '{new_summary}'")
    return {
        "is_contradiction": True,
        "is_update": False,
        "existing_fact": existing["summary"],
        "action": "flag"
    }


async def get_user_contradictions(user_id: UUID) -> list[dict]:
    """Récupère les contradictions flaggées pour un user."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM memory_timeline
            WHERE user_id = $1 AND type = 'contradiction'
            ORDER BY created_at DESC
        """, user_id)
        return [dict(r) for r in rows]


async def resolve_contradiction(event_id: UUID, resolution: str) -> None:
    """
    Résout une contradiction (après clarification avec l'user).

    Args:
        event_id: ID de l'événement contradiction
        resolution: 'keep_old', 'keep_new', 'both_valid'
    """
    async with get_pool().acquire() as conn:
        if resolution == "keep_old":
            # Supprimer la contradiction, garder l'ancien fait
            await conn.execute("""
                DELETE FROM memory_timeline WHERE id = $1
            """, event_id)
        elif resolution == "keep_new":
            # Marquer comme résolu, le nouveau fait est valide
            await conn.execute("""
                UPDATE memory_timeline
                SET type = 'moment', pinned = FALSE
                WHERE id = $1
            """, event_id)
        else:  # both_valid
            # Les deux sont valides (contextes différents)
            await conn.execute("""
                UPDATE memory_timeline
                SET type = 'moment', summary = summary || ' [résolu: contextes différents]'
                WHERE id = $1
            """, event_id)


def _safe_parse_list(value) -> list:
    """Parse une valeur qui peut être une string JSON ou une liste."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def build_memory_reminder(user: dict, relationship: dict) -> str:
    """
    Construit un rappel mémoire à injecter dans le prompt.

    Rappelle à Luna les faits importants pour éviter les inventions.
    """
    parts = []

    # Facts user
    if user.get("name"):
        parts.append(f"Il s'appelle {user['name']}")
    if user.get("age"):
        parts.append(f"Il a {user['age']} ans")
    if user.get("job"):
        parts.append(f"Il travaille comme {user['job']}")
    if user.get("location"):
        parts.append(f"Il habite à {user['location']}")

    # Likes (max 3) - parse JSON if needed
    likes = _safe_parse_list(user.get("likes"))
    if likes:
        # Filter only string likes
        likes_str = [str(l) for l in likes if l and isinstance(l, str)][:3]
        if likes_str:
            parts.append(f"Il aime: {', '.join(likes_str)}")

    # Secrets (si intimacy >= 5)
    if relationship.get("intimacy", 0) >= 5:
        secrets = _safe_parse_list(user.get("secrets"))
        if secrets:
            secrets_str = [str(s) for s in secrets if s and isinstance(s, str)][:2]
            if secrets_str:
                parts.append(f"Secrets partagés: {', '.join(secrets_str)}")

    # Inside jokes - parse JSON if needed
    jokes = _safe_parse_list(relationship.get("inside_jokes"))
    if jokes:
        # Jokes can be strings or dicts with 'trigger' key
        jokes_display = []
        for j in jokes[:2]:
            if isinstance(j, str):
                jokes_display.append(j)
            elif isinstance(j, dict) and j.get("trigger"):
                jokes_display.append(j["trigger"])
        if jokes_display:
            parts.append(f"Vos inside jokes: {', '.join(jokes_display)}")

    if not parts:
        return ""

    return f"""
📝 MÉMOIRE - Ce que tu sais sur lui:
{chr(10).join('- ' + p for p in parts)}

⚠️ RÈGLE: N'invente JAMAIS d'autres détails. Si tu ne sais pas, demande-lui.
"""


def build_dont_invent_reminder() -> str:
    """Rappel pour ne pas inventer."""
    return """
⚠️ RÈGLE ABSOLUE: NE JAMAIS INVENTER

Si tu ne trouves pas une info dans ta mémoire:
✅ "Tu m'en avais jamais parlé non?"
✅ "Rappelle-moi, c'était comment?"
✅ "Je crois pas que tu m'aies dit ça"

❌ JAMAIS inventer des détails
❌ JAMAIS supposer des infos
❌ JAMAIS dire "je me souviens" si pas en mémoire
"""
