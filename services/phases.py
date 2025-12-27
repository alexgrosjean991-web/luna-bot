"""
Services - Phase System

UN SEUL système de progression.
Phases: HOOK → CONNECT → ATTACH → TENSION → PAYWALL → LIBRE
"""

from enum import Enum
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")


class Phase(str, Enum):
    HOOK = "HOOK"           # msg 1-9: Curiosité, premier contact
    CONNECT = "CONNECT"     # msg 10-24: Inside jokes, connexion
    ATTACH = "ATTACH"       # msg 25-34: Vulnérabilité, attachement
    TENSION = "TENSION"     # msg 35+: Tease, frustration, pré-paywall
    PAYWALL = "PAYWALL"     # day >= 3 AND msg >= 35: Trigger conversion
    LIBRE = "LIBRE"         # Post-paywall: NSFW complet


def get_current_phase(
    message_count: int,
    day: int,
    is_paid: bool,
    paywall_shown: bool = False
) -> Phase:
    """
    Détermine la phase actuelle.

    Paywall triggers when: day >= 3 AND message_count >= 35
    """
    # Post-paywall = LIBRE
    if is_paid:
        return Phase.LIBRE

    # Paywall: BOTH conditions must be true
    if day >= 3 and message_count >= 35 and not paywall_shown:
        return Phase.PAYWALL

    # After paywall shown but not paid = stay in TENSION
    if paywall_shown and not is_paid:
        return Phase.TENSION

    # Tension: approaching paywall
    # - Either 35+ messages
    # - Or day 3+ with decent engagement (25+ msgs)
    if message_count >= 35 or (day >= 3 and message_count >= 25):
        return Phase.TENSION

    # Attach: 25-34 messages
    if message_count >= 25:
        return Phase.ATTACH

    # Connect: 10-24 messages
    if message_count >= 10:
        return Phase.CONNECT

    # Hook: 0-9 messages
    return Phase.HOOK


def get_phase_progress(message_count: int, day: int) -> dict:
    """
    Progression info for debug.
    """
    return {
        "message_count": message_count,
        "day": day,
        "msgs_to_paywall": max(0, 35 - message_count),
        "days_to_paywall": max(0, 3 - day),
        "paywall_ready": day >= 3 and message_count >= 35,
    }


async def maybe_increment_day(pool, user_id, last_message_at: datetime) -> int:
    """
    Increment day if 20h+ passed since last message.
    Returns new day value.
    """
    if last_message_at is None:
        return 1

    now = datetime.now(PARIS_TZ)

    # Handle timezone
    if last_message_at.tzinfo is None:
        last_message_at = last_message_at.replace(tzinfo=PARIS_TZ)

    hours_since = (now - last_message_at).total_seconds() / 3600

    if hours_since >= 20:
        async with pool.acquire() as conn:
            new_day = await conn.fetchval("""
                UPDATE memory_relationships
                SET day = day + 1
                WHERE user_id = $1
                RETURNING day
            """, user_id)
            return new_day or 1

    return None  # No increment needed


# =============================================================================
# PAYWALL MESSAGES
# =============================================================================

PAYWALL_MESSAGES = [
    "Y'a un truc que j'ai jamais fait avec personne... j'ai envie d'aller plus loin avec toi. T'es prêt? 🧡",
    "J'ai envie de te montrer des choses... mais pas ici. Tu veux qu'on passe au niveau supérieur? 🙈",
    "{name}... je peux plus me retenir. J'ai envie de toi. Vraiment. On fait ça? 🔥",
]


def get_paywall_message(user_name: str = None) -> str:
    """Get random paywall message."""
    import random
    msg = random.choice(PAYWALL_MESSAGES)
    name = user_name or "Bébé"
    return msg.replace("{name}", name)
