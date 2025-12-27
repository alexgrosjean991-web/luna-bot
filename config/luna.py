"""
Config - Luna Settings

Constantes de configuration uniquement.
La personnalité est dans prompts/luna.py
"""

# =============================================================================
# PROACTIVE MESSAGES CONFIG
# =============================================================================

PROACTIVE_CONFIG = {
    "max_per_day": 2,
    "cooldown_hours": 4,
    "active_hours": (9, 23),  # 9h-23h seulement
}

# =============================================================================
# CLIMAX DETECTION (for NSFW gate)
# =============================================================================

CLIMAX_PATTERNS = [
    # Orgasme explicite
    "j'ai joui", "je jouis", "je viens de jouir", "tu m'as fait jouir",
    # État post-orgasme
    "je tremble encore", "je tremble de partout",
    "je suis épuisée", "épuisée là",
    # Aftercare phrases
    "c'était incroyable", "c'était trop bon",
]
