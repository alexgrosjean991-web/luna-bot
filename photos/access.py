"""
Photo access control for Luna Bot.

Determines if a user can see a specific photo category based on:
- Phase
- Trust level
- Subscription status
- NSFW tier
"""

import random
from enum import Enum
from typing import Optional

from core import get_logger

logger = get_logger(__name__)


class PhotoCategory(Enum):
    """Photo categories with access requirements."""
    PIXEL = "pixel"              # Luna's cat - always available
    SELFIE_SFW = "selfie_sfw"    # Safe selfies - trust 20+
    OUTFIT = "outfit"            # Outfit photos - phase interest+, trust 30+
    SUGGESTIVE = "suggestive"    # Suggestive - phase connection+, tier 2+, trust 40+
    NSFW_SOFT = "nsfw_soft"      # Lingerie - phase intimacy+, tier 2+, subscriber, trust 50+
    NSFW_EXPLICIT = "nsfw_explicit"  # Explicit - phase intimacy+, tier 3, subscriber, trust 60+


# Access requirements per category
ACCESS_REQUIREMENTS = {
    PhotoCategory.PIXEL: {
        "trust_min": 0,
        "phases": ["HOOK", "CONNECT", "ATTACH", "TENSION", "PAYWALL", "LIBRE"],
        "tier_min": 0,
        "subscriber_required": False,
    },
    PhotoCategory.SELFIE_SFW: {
        "trust_min": 20,
        "phases": ["HOOK", "CONNECT", "ATTACH", "TENSION", "PAYWALL", "LIBRE"],
        "tier_min": 0,
        "subscriber_required": False,
    },
    PhotoCategory.OUTFIT: {
        "trust_min": 30,
        "phases": ["CONNECT", "ATTACH", "TENSION", "PAYWALL", "LIBRE"],
        "tier_min": 0,
        "subscriber_required": False,
    },
    PhotoCategory.SUGGESTIVE: {
        "trust_min": 40,
        "phases": ["ATTACH", "TENSION", "PAYWALL", "LIBRE"],
        "tier_min": 2,
        "subscriber_required": False,
    },
    PhotoCategory.NSFW_SOFT: {
        "trust_min": 50,
        "phases": ["LIBRE"],
        "tier_min": 2,
        "subscriber_required": True,
    },
    PhotoCategory.NSFW_EXPLICIT: {
        "trust_min": 60,
        "phases": ["LIBRE"],
        "tier_min": 3,
        "subscriber_required": True,
    },
}


def check_access(
    category: PhotoCategory,
    phase: str,
    trust_score: int = 0,
    nsfw_tier: int = 1,
    is_subscriber: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Check if user can access a photo category.

    Args:
        category: Photo category to check
        phase: Current relationship phase
        trust_score: User's trust score (0-100)
        nsfw_tier: Current NSFW tier (1-3)
        is_subscriber: Is user a paying subscriber

    Returns:
        (can_access, denial_reason)
    """
    req = ACCESS_REQUIREMENTS.get(category)
    if not req:
        return False, "unknown_category"

    # Check phase
    if phase not in req["phases"]:
        return False, "wrong_phase"

    # Check trust
    if trust_score < req["trust_min"]:
        return False, "trust_too_low"

    # Check tier
    if nsfw_tier < req["tier_min"]:
        return False, "tier_too_low"

    # Check subscription
    if req["subscriber_required"] and not is_subscriber:
        return False, "not_subscriber"

    return True, None


# =============================================================================
# DENIAL MESSAGES (Luna style)
# =============================================================================

DENIAL_MESSAGES = {
    "wrong_phase": [
        "hm pas maintenant",
        "on se connait pas assez encore",
        "patience, je suis pas comme ça",
    ],
    "trust_too_low": [
        "tu me connais pas assez",
        "faut que je te fasse confiance d'abord",
        "on verra plus tard peut-être",
    ],
    "tier_too_low": [
        "là c'est pas le moment",
        "on est pas dans ce mood là",
        "change de sujet",
    ],
    "not_subscriber": [
        "ça c'est réservé à ceux qui me soutiennent",
        "faut débloquer avant",
        "tu veux voir? faut payer",
    ],
    "unknown_category": [
        "hein? je vois pas de quoi tu parles",
    ],
}


def get_denial_message(reason: str) -> str:
    """Get a random denial message for the given reason."""
    messages = DENIAL_MESSAGES.get(reason, DENIAL_MESSAGES["unknown_category"])
    return random.choice(messages)
