"""
Progression System - Gestion des transitions de jours

Critères pour passer au jour suivant:
- Temps minimum depuis début du jour actuel (20h)
- Nombre minimum de messages (15)
- Score d'intimacy minimum (variable par jour)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Heures minimum avant de pouvoir passer au jour suivant
MIN_HOURS_PER_DAY = 20

# Messages minimum (user messages seulement) pour passer au jour suivant
MIN_MESSAGES_PER_DAY = 15

# Intimacy minimum requise pour chaque transition
# day 1→2 = intimacy 2, day 2→3 = intimacy 3, etc.
INTIMACY_THRESHOLDS = {
    1: 2,   # Pour passer de J1 à J2
    2: 3,   # Pour passer de J2 à J3
    3: 4,   # Pour passer de J3 à J4
    4: 6,   # Pour passer de J4 à J5
    5: 10,  # J5 = max, pas de transition
}

# Jour maximum
MAX_DAY = 5


# =============================================================================
# PROGRESSION STATE
# =============================================================================

async def get_progression_state(pool, user_id: UUID) -> dict:
    """
    Récupère l'état de progression d'un utilisateur.

    Returns:
        {
            "day": int,
            "intimacy": int,
            "trust": int,
            "day_started_at": datetime,
            "messages_today": int,
            "hours_since_day_start": float,
            "can_progress": bool,
            "progress_blockers": list[str],
        }
    """
    async with pool.acquire() as conn:
        # Get relationship data
        rel = await conn.fetchrow("""
            SELECT r.day, r.intimacy, r.trust, r.day_started_at, r.first_contact
            FROM memory_relationships r
            JOIN memory_users u ON r.user_id = u.id
            WHERE r.user_id = $1
        """, user_id)

        if not rel:
            return None

        day = rel["day"]
        intimacy = rel["intimacy"]
        trust = rel["trust"]

        # day_started_at peut être NULL pour les anciens users
        day_started_at = rel["day_started_at"] or rel["first_contact"]

        # Compter les messages user depuis le début du jour actuel
        messages_today = await conn.fetchval("""
            SELECT COUNT(*) FROM conversations_simple
            WHERE user_id = $1
            AND role = 'user'
            AND created_at >= $2
        """, user_id, day_started_at)

        # Calculer le temps écoulé depuis le début du jour
        now = datetime.now(PARIS_TZ)
        if day_started_at.tzinfo is None:
            day_started_at = day_started_at.replace(tzinfo=PARIS_TZ)
        hours_since = (now - day_started_at).total_seconds() / 3600

        # Vérifier si peut progresser
        can_progress, blockers = _check_progression_criteria(
            day, intimacy, messages_today, hours_since
        )

        return {
            "day": day,
            "intimacy": intimacy,
            "trust": trust,
            "day_started_at": day_started_at,
            "messages_today": messages_today,
            "hours_since_day_start": round(hours_since, 1),
            "can_progress": can_progress,
            "progress_blockers": blockers,
        }


def _check_progression_criteria(
    day: int,
    intimacy: int,
    messages: int,
    hours: float
) -> tuple[bool, list[str]]:
    """
    Vérifie si les critères de progression sont remplis.

    Returns:
        (can_progress: bool, blockers: list[str])
    """
    blockers = []

    # Jour max atteint
    if day >= MAX_DAY:
        return False, ["max_day_reached"]

    # Check temps minimum
    if hours < MIN_HOURS_PER_DAY:
        remaining = MIN_HOURS_PER_DAY - hours
        blockers.append(f"time:{remaining:.1f}h_remaining")

    # Check messages minimum
    if messages < MIN_MESSAGES_PER_DAY:
        remaining = MIN_MESSAGES_PER_DAY - messages
        blockers.append(f"messages:{remaining}_remaining")

    # Check intimacy minimum
    required_intimacy = INTIMACY_THRESHOLDS.get(day, 10)
    if intimacy < required_intimacy:
        blockers.append(f"intimacy:{intimacy}/{required_intimacy}")

    can_progress = len(blockers) == 0
    return can_progress, blockers


# =============================================================================
# PROGRESSION ACTIONS
# =============================================================================

async def check_and_progress(pool, user_id: UUID) -> dict:
    """
    Vérifie si l'utilisateur peut progresser et effectue la transition si oui.

    Returns:
        {
            "progressed": bool,
            "old_day": int,
            "new_day": int,
            "blockers": list[str],  # Si pas progressé
        }
    """
    state = await get_progression_state(pool, user_id)

    if not state:
        return {"progressed": False, "error": "user_not_found"}

    if not state["can_progress"]:
        return {
            "progressed": False,
            "old_day": state["day"],
            "new_day": state["day"],
            "blockers": state["progress_blockers"],
        }

    # Effectuer la transition
    new_day = state["day"] + 1

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET day = $2,
                day_started_at = NOW(),
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, new_day)

    logger.info(f"User {user_id} progressed: Day {state['day']} → Day {new_day}")

    return {
        "progressed": True,
        "old_day": state["day"],
        "new_day": new_day,
        "blockers": [],
    }


async def force_progress(pool, user_id: UUID, target_day: int) -> dict:
    """
    Force la progression vers un jour spécifique (admin only).

    Args:
        target_day: Jour cible (1-5)
    """
    if target_day < 1 or target_day > MAX_DAY:
        return {"error": f"invalid_day, must be 1-{MAX_DAY}"}

    async with pool.acquire() as conn:
        old = await conn.fetchval("""
            SELECT day FROM memory_relationships WHERE user_id = $1
        """, user_id)

        await conn.execute("""
            UPDATE memory_relationships
            SET day = $2,
                day_started_at = NOW(),
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, target_day)

    logger.info(f"User {user_id} FORCE progressed: Day {old} → Day {target_day}")

    return {
        "progressed": True,
        "old_day": old,
        "new_day": target_day,
        "forced": True,
    }


# =============================================================================
# INTIMACY UPDATES
# =============================================================================

# Actions qui augmentent l'intimacy
INTIMACY_ACTIONS = {
    "user_shared_secret": 2,      # User partage un secret
    "user_vulnerability": 2,      # User se montre vulnérable
    "user_compliment": 1,         # User fait un compliment sincère
    "long_conversation": 1,       # Conversation > 20 messages
    "user_asked_about_luna": 1,   # User s'intéresse à Luna
    "flirt_reciprocated": 1,      # User répond au flirt
    "sexto_completed": 2,         # Sexto terminé (J4+)
}

# Actions qui diminuent l'intimacy
INTIMACY_PENALTIES = {
    "user_rude": -1,              # User impoli
    "user_pushy": -1,             # User insistant/pressant
    "user_ghosted": -2,           # User disparaît > 48h
}


async def update_intimacy(pool, user_id: UUID, action: str) -> int:
    """
    Met à jour l'intimacy basé sur une action.

    Returns:
        Nouveau score d'intimacy
    """
    delta = INTIMACY_ACTIONS.get(action) or INTIMACY_PENALTIES.get(action, 0)

    if delta == 0:
        logger.warning(f"Unknown intimacy action: {action}")
        return None

    async with pool.acquire() as conn:
        new_intimacy = await conn.fetchval("""
            UPDATE memory_relationships
            SET intimacy = LEAST(10, GREATEST(1, intimacy + $2)),
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING intimacy
        """, user_id, delta)

    logger.debug(f"User {user_id} intimacy {'+' if delta > 0 else ''}{delta} → {new_intimacy}")
    return new_intimacy


async def detect_intimacy_action(message: str, context: dict) -> Optional[str]:
    """
    Détecte automatiquement les actions d'intimacy dans un message.

    Args:
        message: Message de l'utilisateur
        context: Contexte (day, history, etc.)

    Returns:
        Action détectée ou None
    """
    msg_lower = message.lower()

    # Patterns de vulnérabilité
    vulnerability_patterns = [
        "j'ai peur", "je me sens seul", "personne me comprend",
        "c'est dur", "j'en peux plus", "je suis triste",
        "j'ai jamais dit ça", "secret", "confiance"
    ]

    # Patterns de compliments
    compliment_patterns = [
        "t'es belle", "t'es incroyable", "j'aime bien",
        "tu me plais", "t'es différente", "spéciale"
    ]

    # Patterns d'intérêt pour Luna
    interest_patterns = [
        "et toi", "parle moi de toi", "c'est quoi ton",
        "tu fais quoi", "t'aimes quoi", "raconte"
    ]

    # Patterns impolis
    rude_patterns = [
        "ta gueule", "ferme la", "t'es conne", "nique",
        "je m'en fous", "osef"
    ]

    # Check patterns
    for pattern in vulnerability_patterns:
        if pattern in msg_lower:
            return "user_vulnerability"

    for pattern in compliment_patterns:
        if pattern in msg_lower:
            return "user_compliment"

    for pattern in interest_patterns:
        if pattern in msg_lower:
            return "user_asked_about_luna"

    for pattern in rude_patterns:
        if pattern in msg_lower:
            return "user_rude"

    return None
