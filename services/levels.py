"""
Système de niveaux de conversation Luna.
Version simplifiée: 3 niveaux + cooldown.
"""

from enum import IntEnum
import re
import logging

logger = logging.getLogger(__name__)


class ConversationLevel(IntEnum):
    """Niveaux de conversation."""
    SFW = 1      # Normal, flirt léger
    TENSION = 2  # Build-up, sous-entendus
    NSFW = 3     # Explicite


class EmotionalState(IntEnum):
    """État émotionnel détecté."""
    NEUTRAL = 0
    POSITIVE = 1
    NEGATIVE = 2  # Bloque escalade


# ============== PATTERNS DE DÉTECTION ==============

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
    'embrasse', 'caresse', 'touche', 'corps', 'peau'
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


# ============== GESTIONNAIRE DE TRANSITIONS ==============

class TransitionManager:
    """Gère les transitions entre niveaux."""

    # Config
    MIN_MESSAGES_BEFORE_NSFW = 5       # Messages minimum avant NSFW
    MIN_DAYS_BEFORE_NSFW = 3           # Jours minimum avant NSFW
    COOLDOWN_MESSAGES = 5              # Messages de cooldown après NSFW
    MESSAGES_BETWEEN_LEVELS = 2        # Messages entre changements de niveau

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
        Décide de la transition à effectuer.

        Returns:
            (target_level, reason, prompt_modifier)
        """
        # RÈGLE 1: Émotion négative → bloquer escalade
        if emotional_state == EmotionalState.NEGATIVE:
            return (
                ConversationLevel.SFW,
                "emotional_block",
                "USER_DISTRESSED"
            )

        # RÈGLE 2: En cooldown → forcer SFW
        if cooldown_remaining > 0:
            return (
                ConversationLevel.SFW,
                "in_cooldown",
                "AFTERCARE"
            )

        # RÈGLE 3: Trop tôt (avant jour 3) → max TENSION
        if day_count < TransitionManager.MIN_DAYS_BEFORE_NSFW:
            if detected_level >= ConversationLevel.NSFW:
                return (
                    ConversationLevel.TENSION,
                    "too_early",
                    "DELAY_GRATIFICATION"
                )

        # RÈGLE 4: Pas assez de messages en session → max TENSION
        if detected_level >= ConversationLevel.NSFW:
            if messages_this_session < TransitionManager.MIN_MESSAGES_BEFORE_NSFW:
                return (
                    ConversationLevel.TENSION,
                    "session_too_short",
                    "BUILD_TENSION"
                )

        # RÈGLE 5: Trop rapide entre niveaux → garder actuel
        if detected_level > current_level:
            if messages_since_level_change < TransitionManager.MESSAGES_BETWEEN_LEVELS:
                return (
                    ConversationLevel(current_level),
                    "too_fast",
                    "BUILD_TENSION"
                )

        # RÈGLE 6: Max +1 niveau par transition
        if detected_level > current_level + 1:
            return (
                ConversationLevel(current_level + 1),
                "gradual_escalation",
                None
            )

        # OK: suivre le niveau détecté
        return (
            detected_level,
            "user_lead",
            None
        )
