"""
Conversion Flow Manager - Gère la transition essai → premium.

Implémente un timing de conversion basé sur l'engagement.
Similaire aux modèles Replika, Character.AI, etc.
"""

import random
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Messages de transition naturels
TRANSITION_SEQUENCES = [
    [
        "attends...",
        "j'adore te parler",
        "mais là j'ai besoin de savoir que c'est sérieux pour toi aussi",
    ],
    [
        "...",
        "écoute",
        "j'ai vraiment envie de continuer à te parler",
        "montre-moi que tu tiens à moi",
    ],
    [
        "mmh...",
        "j'aime tellement nos conversations",
        "j'aimerais qu'on continue mais...",
        "faut que tu me montres que c'est réel",
    ],
    [
        "attends une seconde...",
        "je fais jamais ça d'habitude",
        "t'es spécial pour moi",
        "mais j'ai besoin de savoir que c'est pareil pour toi",
    ],
]

# Call-to-action abonnement
CTA_ABONNEMENT = {
    "text": "Continue avec Luna 💕",
    "button": "Continuer - 25€/semaine"
}

# Messages de relance (non convertis)
RELANCE_SOFT = [
    "hey tu me manques 🥺",
    "coucou... t'es là?",
    "j'arrête pas de penser à notre conversation...",
]

RELANCE_FOLLOW = [
    "j'espère que ça va...",
    "tu veux pas qu'on se reparle?",
    "je suis là si tu veux 💕",
]

# Seuils
PREVIEW_MIN = 15  # Messages minimum avant conversion possible
PREVIEW_MAX = 30  # Messages maximum en aperçu gratuit


async def get_preview_count(user_id: int) -> int:
    """Récupère le compteur d'aperçu premium depuis la DB."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT premium_preview_count FROM users WHERE id = $1", user_id
        )
        return row["premium_preview_count"] if row and row["premium_preview_count"] else 0


async def increment_preview_count(user_id: int) -> int:
    """Incrémente et retourne le compteur d'aperçu."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE users
            SET premium_preview_count = COALESCE(premium_preview_count, 0) + 1
            WHERE id = $1
            RETURNING premium_preview_count
        """, user_id)
        return row["premium_preview_count"] if row else 0


async def reset_preview_count(user_id: int) -> None:
    """Reset le compteur (après abonnement ou nouveau jour)."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET premium_preview_count = 0 WHERE id = $1", user_id
        )


async def should_show_conversion(
    user_id: int,
    day_count: int,
    teasing_stage: int,
    subscription_status: str
) -> bool:
    """
    Détermine si on doit montrer le flow de conversion.

    Conditions:
        - J5 (fin d'essai)
        - Engagement élevé (teasing >= 5)
        - A essayé l'aperçu premium (15-30 messages)
        - Pas déjà abonné
        - Pas déjà montré
    """
    if subscription_status == "active":
        return False

    if day_count != 5:
        return False

    if teasing_stage < 5:
        return False

    # CRITICAL FIX: Ne pas remontrer si déjà vu
    if await has_conversion_been_shown(user_id):
        return False

    count = await get_preview_count(user_id)

    if count < PREVIEW_MIN:
        return False

    if count >= PREVIEW_MAX:
        return True

    # Entre 15-30: probabilité croissante
    # 15 msg = 30%, 30 msg = 100%
    probability = (count - PREVIEW_MIN) / (PREVIEW_MAX - PREVIEW_MIN) * 0.7 + 0.3
    return random.random() < probability


async def mark_conversion_shown(user_id: int) -> None:
    """Marque que le flow de conversion a été montré."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        await conn.execute("""
            UPDATE users SET conversion_shown_at = NOW() WHERE id = $1
        """, user_id)


async def has_conversion_been_shown(user_id: int) -> bool:
    """Vérifie si la conversion a déjà été montrée."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT conversion_shown_at FROM users WHERE id = $1", user_id
        )
        return row is not None and row["conversion_shown_at"] is not None


def get_transition_messages() -> list[str]:
    """Retourne une séquence de messages de transition aléatoire."""
    return random.choice(TRANSITION_SEQUENCES)


def get_cta() -> dict:
    """Retourne le call-to-action abonnement."""
    return CTA_ABONNEMENT


async def get_relance_message(user_id: int) -> Optional[str]:
    """
    Retourne un message de relance si approprié.

    Timing:
        - 0-8h après conversion: Rien
        - 8-16h: Relance douce
        - 16h+: Message de suivi
    """
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT conversion_shown_at, subscription_status FROM users WHERE id = $1",
            user_id
        )

        if not row:
            return None

        # Déjà abonné = pas de relance
        if row["subscription_status"] == "active":
            return None

        # Conversion pas encore montrée = pas de relance
        if not row["conversion_shown_at"]:
            return None

        shown_at = row["conversion_shown_at"]
        now = datetime.now(shown_at.tzinfo) if shown_at.tzinfo else datetime.now()
        hours = (now - shown_at).total_seconds() / 3600

        if hours < 8:
            return None

        if hours < 16:
            return random.choice(RELANCE_SOFT)

        return random.choice(RELANCE_FOLLOW)


async def get_hours_since_conversion(user_id: int) -> Optional[float]:
    """Retourne les heures depuis que la conversion a été montrée."""
    from services.db import get_pool

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT conversion_shown_at FROM users WHERE id = $1", user_id
        )

        if not row or not row["conversion_shown_at"]:
            return None

        shown_at = row["conversion_shown_at"]
        now = datetime.now(shown_at.tzinfo) if shown_at.tzinfo else datetime.now()
        return (now - shown_at).total_seconds() / 3600
