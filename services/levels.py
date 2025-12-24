"""
Système de niveaux de conversation Luna.
V3: Simplifié - garde detect_level pour compatibilité, momentum.py gère les transitions.
"""

from enum import IntEnum
import re
import logging

logger = logging.getLogger(__name__)


class ConversationLevel(IntEnum):
    """Niveaux de conversation (legacy, gardé pour compatibilité)."""
    SFW = 1      # Normal, flirt léger
    TENSION = 2  # Build-up, sous-entendus
    NSFW = 3     # Explicite


class EmotionalState(IntEnum):
    """État émotionnel détecté."""
    NEUTRAL = 0
    POSITIVE = 1
    NEGATIVE = 2  # Bloque escalade


# ============== PATTERNS DE DÉTECTION ==============
# Note: Ces patterns sont aussi dans momentum.py, gardés ici pour legacy

NSFW_KEYWORDS = [
    'baise', 'suce', 'bite', 'chatte', 'jouir', 'jouis', 'orgasme',
    'pénètre', 'enfonce', 'gémis', 'encule', 'sodomise',
    'avale', 'éjacule', 'levrette', 'doigte', 'branle',
    'sperme', 'mouillée', 'trempée', 'bandé'
]

NSFW_PATTERNS = [
    r'je (?:te |)baise',
    r'suce[\- ]?(?:moi|la)',
    r'je (?:vais |)jouir',
    r'dans (?:ta |ma )(?:chatte|bouche|cul)',
    r'(?:j\'ai |je suis )(?:trop |)(?:mouillée|excitée|bandé)',
    r'(?:enlève|retire) (?:ton|ta|tes)',
    r'(?:mets|prends)[\- ]?(?:la|moi)',
]

TENSION_KEYWORDS = [
    'envie de toi', 'te veux', 'si tu étais là', 'imagine',
    'rêvé de toi', 'pense à toi', 'me manque', 'chaud', 'chaude',
    'excité', 'seul dans mon lit', 'nue', 'nu', 'déshabille',
    'embrasse', 'caresse', 'touche', 'corps', 'peau',
    'string', 'culotte', 'soutif', 'sous-vêtements', 'sexy'
]

TENSION_PATTERNS = [
    r'si (?:tu étais|t\'étais) là',
    r'j\'ai (?:tellement |trop |)envie de toi',
    r'je (?:te |)veux',
    r'qu\'est-ce que tu (?:me |)(?:ferais|fais)',
    r'tu me manques',
    r'je pense à toi',
]

NEGATIVE_EMOTION_PATTERNS = [
    r'je (?:suis |me sens )(?:triste|mal|déprimé|seul|anxieux|pas bien)',
    r'j\'ai (?:envie de |)(?:pleurer|mourir)',
    r'personne (?:ne |)(?:m\'aime|me comprend)',
    r'j\'en (?:peux |ai )plus',
    r'ça (?:va |)(?:pas|plus)',
    r'je (?:vais |)(?:pas bien|mal)',
]


def detect_level(message: str) -> tuple[ConversationLevel, EmotionalState]:
    """
    Détecte le niveau de conversation et l'état émotionnel.
    LEGACY: Utilisé pour compatibilité, préférer momentum.classify_intensity()

    Returns:
        (ConversationLevel, EmotionalState)
    """
    msg_lower = message.lower()

    # 1. Détecter émotion négative d'abord
    for pattern in NEGATIVE_EMOTION_PATTERNS:
        if re.search(pattern, msg_lower):
            logger.info(f"Negative emotion detected in: {message[:50]}")
            return ConversationLevel.SFW, EmotionalState.NEGATIVE

    # 2. Détecter NSFW
    for keyword in NSFW_KEYWORDS:
        if keyword in msg_lower:
            return ConversationLevel.NSFW, EmotionalState.NEUTRAL

    for pattern in NSFW_PATTERNS:
        if re.search(pattern, msg_lower):
            return ConversationLevel.NSFW, EmotionalState.NEUTRAL

    # 3. Détecter TENSION
    for keyword in TENSION_KEYWORDS:
        if keyword in msg_lower:
            return ConversationLevel.TENSION, EmotionalState.NEUTRAL

    for pattern in TENSION_PATTERNS:
        if re.search(pattern, msg_lower):
            return ConversationLevel.TENSION, EmotionalState.NEUTRAL

    # 4. Default: SFW
    return ConversationLevel.SFW, EmotionalState.NEUTRAL


def detect_climax(message: str) -> bool:
    """Détecte si le message indique un climax (fin de session NSFW)."""
    patterns = [
        r'je (?:vais |)jouir',
        r'je jouis',
        r'j\'ai joui',
        r'c\'était (?:bon|incroyable|wow|trop bon)',
        r'ahh+',
        r'💦.*💦',
    ]
    msg_lower = message.lower()
    return any(re.search(p, msg_lower) for p in patterns)


# ============== LEGACY: TransitionManager (DEPRECATED) ==============
# Gardé pour compatibilité pendant la migration
# V3 utilise momentum.py à la place

class TransitionManager:
    """
    DEPRECATED: Utilisez momentum.py à la place.
    Gardé pour compatibilité pendant la migration.
    """

    MIN_MESSAGES_BEFORE_NSFW = 5
    MIN_DAYS_BEFORE_NSFW = 3
    COOLDOWN_MESSAGES = 5
    MESSAGES_BETWEEN_LEVELS = 2

    @staticmethod
    def decide_transition(
        current_level: int,
        detected_level: ConversationLevel,
        emotional_state: EmotionalState,
        day_count: int,
        messages_this_session: int,
        cooldown_remaining: int,
        messages_since_level_change: int
    ) -> tuple[ConversationLevel, str, str | None]:
        """
        DEPRECATED: Cette méthode est gardée pour compatibilité.
        V3 utilise momentum.apply_soft_cap() à la place.
        """
        logger.warning("TransitionManager.decide_transition is DEPRECATED, use momentum.py")

        # Émotion négative → bloquer escalade
        if emotional_state == EmotionalState.NEGATIVE:
            return (ConversationLevel.SFW, "emotional_block", "USER_DISTRESSED")

        # En cooldown → forcer SFW
        if cooldown_remaining > 0:
            return (ConversationLevel.SFW, "in_cooldown", "AFTERCARE")

        # Trop tôt (avant jour 3) → max TENSION
        if day_count < TransitionManager.MIN_DAYS_BEFORE_NSFW:
            if detected_level >= ConversationLevel.NSFW:
                return (ConversationLevel.TENSION, "too_early", "NSFW_TEASE")

        # Pas assez de messages en session → max TENSION
        if detected_level >= ConversationLevel.NSFW:
            if messages_this_session < TransitionManager.MIN_MESSAGES_BEFORE_NSFW:
                return (ConversationLevel.TENSION, "session_too_short", "NSFW_TEASE")

        # Max +1 niveau par transition
        if detected_level > current_level + 1:
            return (ConversationLevel(current_level + 1), "gradual_escalation", None)

        return (detected_level, "user_lead", None)
