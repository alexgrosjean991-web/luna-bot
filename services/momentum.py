"""
Luna V3 Momentum Engine.

Calculates conversation momentum (0-100) based on:
- Message content intensity
- Session duration
- Historical engagement

Replaces the V7 TransitionManager with a smoother, momentum-based approach.
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Intensity(str, Enum):
    """Message intensity levels."""
    SFW = "SFW"
    FLIRT = "FLIRT"
    HOT = "HOT"
    NSFW = "NSFW"


@dataclass
class SoftCapResult:
    """Result of soft cap application."""
    tier: int              # 1, 2, or 3
    modifier: str | None   # Prompt modifier to apply
    instruction: str       # Instruction for Luna


# ============== INTENSITY PATTERNS ==============

# NSFW: Explicit sexual content
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

# HOT: Very suggestive, physical desire
HOT_KEYWORDS = [
    'envie de toi', 'te veux', 'j\'ai envie', 'tellement envie',
    'corps', 'peau', 'mains sur', 'toucher', 'caresser',
    'nu', 'nue', 'déshabille', 'string', 'culotte',
    'lit', 'chaud', 'chaude', 'excité', 'excitée',
    'embrasser', 'bouche', 'lèvres'
]

HOT_PATTERNS = [
    r'j\'ai (?:tellement |trop |)envie de toi',
    r'je (?:te |)veux',
    r'si (?:tu étais|t\'étais) là',
    r'dans (?:mon |ton )lit',
    r'(?:tes |mes )mains sur',
]

# FLIRT: Light flirting, romantic interest
FLIRT_KEYWORDS = [
    'mignon', 'belle', 'beau', 'canon', 'craquant',
    'pense à toi', 'tu me manques', 'manque', 'rêvé de toi',
    'adorable', 'sexy', 'attiré', 't\'aime bien',
    'hâte de te voir', 'sourire'
]

FLIRT_PATTERNS = [
    r'tu me manques',
    r'je pense à toi',
    r't\'es (?:trop |)(?:mignon|beau|canon)',
    r'j\'(?:aime|adore) (?:bien |)(?:parler avec toi|te parler)',
]

# Negative emotions: Block escalation
NEGATIVE_PATTERNS = [
    r'je (?:suis |me sens )(?:triste|mal|déprimé|seul|anxieux|pas bien)',
    r'j\'ai (?:envie de |)(?:pleurer|mourir)',
    r'personne (?:ne |)(?:m\'aime|me comprend)',
    r'j\'en (?:peux |ai )plus',
    r'ça (?:va |)(?:pas|plus)',
    r'je (?:vais |)(?:pas bien|mal)',
]

# Climax indicators
CLIMAX_PATTERNS = [
    r'je (?:vais |)jouir',
    r'je jouis',
    r'j\'ai joui',
    r'c\'était (?:bon|incroyable|wow|trop bon)',
    r'ahh+',
    r'💦.*💦',
]


class MomentumEngine:
    """
    Calculates and manages conversation momentum.

    Momentum is a 0-100 score that represents the "heat" of the conversation.
    Higher momentum = more intimate/explicit content allowed.
    """

    # Scoring constants
    INTENSITY_SCORES = {
        Intensity.SFW: 0,
        Intensity.FLIRT: 15,
        Intensity.HOT: 35,
        Intensity.NSFW: 60
    }

    # Decay and bonuses
    DECAY_FACTOR = 0.85          # Momentum decays if not maintained
    SESSION_BONUS = 3            # Bonus per message in session
    MAX_MOMENTUM = 100

    # Tier thresholds (base, adjusted by intimacy_history)
    BASE_TIER2_THRESHOLD = 35
    BASE_TIER3_THRESHOLD = 65

    def classify_intensity(self, message: str) -> tuple[Intensity, bool]:
        """
        Classify message intensity using regex patterns.

        Returns:
            (intensity, is_negative_emotion)
        """
        msg_lower = message.lower()

        # Check negative emotions first
        for pattern in NEGATIVE_PATTERNS:
            if re.search(pattern, msg_lower):
                logger.info(f"Negative emotion detected")
                return Intensity.SFW, True

        # Check NSFW
        for keyword in NSFW_KEYWORDS:
            if keyword in msg_lower:
                return Intensity.NSFW, False
        for pattern in NSFW_PATTERNS:
            if re.search(pattern, msg_lower):
                return Intensity.NSFW, False

        # Check HOT
        for keyword in HOT_KEYWORDS:
            if keyword in msg_lower:
                return Intensity.HOT, False
        for pattern in HOT_PATTERNS:
            if re.search(pattern, msg_lower):
                return Intensity.HOT, False

        # Check FLIRT
        for keyword in FLIRT_KEYWORDS:
            if keyword in msg_lower:
                return Intensity.FLIRT, False
        for pattern in FLIRT_PATTERNS:
            if re.search(pattern, msg_lower):
                return Intensity.FLIRT, False

        return Intensity.SFW, False

    def calculate_momentum(
        self,
        message: str,
        current_momentum: float,
        messages_this_session: int,
        day_count: int
    ) -> tuple[float, Intensity, bool]:
        """
        Calculate new momentum based on message and context.

        Formula:
            new_momentum = (current * decay) + intensity_score + session_bonus

        Returns:
            (new_momentum, intensity, is_negative)
        """
        intensity, is_negative = self.classify_intensity(message)

        # If negative emotion, don't escalate
        if is_negative:
            # Gentle decay, don't reset completely
            new_momentum = current_momentum * 0.7
            logger.info(f"Negative emotion: momentum {current_momentum:.1f} → {new_momentum:.1f}")
            return new_momentum, intensity, True

        # Calculate new momentum
        intensity_score = self.INTENSITY_SCORES[intensity]
        session_bonus = min(messages_this_session * self.SESSION_BONUS, 20)  # Cap at 20

        # Apply decay then add new score
        decayed = current_momentum * self.DECAY_FACTOR
        new_momentum = decayed + intensity_score + session_bonus

        # Cap at max
        new_momentum = min(new_momentum, self.MAX_MOMENTUM)

        logger.info(
            f"Momentum: {current_momentum:.1f} → {new_momentum:.1f} "
            f"(intensity={intensity.value}, session_bonus={session_bonus})"
        )

        return new_momentum, intensity, False

    def get_tier_thresholds(self, intimacy_history: int) -> tuple[int, int]:
        """
        Get tier thresholds adjusted by intimacy history.

        More intimate history = lower thresholds (faster escalation).
        """
        if intimacy_history == 0:
            # New user: higher thresholds
            return 40, 70
        elif intimacy_history < 3:
            # Some history
            return 35, 60
        elif intimacy_history < 10:
            # Regular user
            return 25, 50
        else:
            # Very intimate history
            return 20, 40

    def get_tier(
        self,
        momentum: float,
        day_count: int,
        intimacy_history: int
    ) -> int:
        """
        Determine tier (1, 2, or 3) based on momentum and context.

        Tier 1: Haiku SFW
        Tier 2: Magnum Flirt
        Tier 3: Magnum NSFW
        """
        tier2_threshold, tier3_threshold = self.get_tier_thresholds(intimacy_history)

        if momentum >= tier3_threshold:
            return 3
        elif momentum >= tier2_threshold:
            return 2
        return 1

    def apply_soft_cap(
        self,
        intensity: Intensity,
        day_count: int,
        messages_this_session: int,
        momentum: float
    ) -> SoftCapResult:
        """
        Apply soft caps based on relationship phase.

        NEVER returns hard rejections - always seductive redirections.
        """
        # Phase Discovery (J1-2)
        if day_count <= 2:
            if momentum > 50:
                return SoftCapResult(
                    tier=2,
                    modifier="SOFT_REDIRECT",
                    instruction="Montre de l'intérêt mais ralentis avec charme: "
                               "'on se connaît à peine... mais j'aime bien où ça va 😏'"
                )
            elif momentum > 30:
                return SoftCapResult(
                    tier=2,
                    modifier="GENTLE_SLOW",
                    instruction="Tu peux flirter mais reste légère: "
                               "'doucement... on a le temps 💕'"
                )

        # Phase Connection (J3-5)
        elif day_count <= 5:
            if momentum > 70:
                return SoftCapResult(
                    tier=2,
                    modifier="TEASE_PATIENCE",
                    instruction="Tease avec promesse: "
                               "'patience... bientôt 😏 tu me rends folle'"
                )
            elif momentum > 50:
                return SoftCapResult(
                    tier=2,
                    modifier=None,
                    instruction="Tu peux être très suggestive, parler de désir"
                )

        # Phase Attachment (J6+): No caps
        # Luna can follow user's lead fully

        # Default: No cap applied
        return SoftCapResult(
            tier=self.get_tier(momentum, day_count, 0),
            modifier=None,
            instruction=""
        )

    def detect_climax(self, message: str) -> bool:
        """Detect if message indicates climax."""
        msg_lower = message.lower()
        return any(re.search(p, msg_lower) for p in CLIMAX_PATTERNS)

    def apply_climax_cooldown(self, current_momentum: float) -> float:
        """
        Apply cooldown after climax.

        Reduces momentum to 30% (not full reset).
        """
        new_momentum = current_momentum * 0.3
        logger.info(f"Climax cooldown: momentum {current_momentum:.1f} → {new_momentum:.1f}")
        return new_momentum

    def get_recovery_modifier(self, messages_since_climax: int) -> str | None:
        """
        Get appropriate modifier based on recovery phase.

        Messages 1-3: AFTERCARE
        Messages 4-6: POST_INTIMATE
        Messages 7+: Normal
        """
        if messages_since_climax <= 3:
            return "AFTERCARE"
        elif messages_since_climax <= 6:
            return "POST_INTIMATE"
        return None


# Singleton instance
momentum_engine = MomentumEngine()
