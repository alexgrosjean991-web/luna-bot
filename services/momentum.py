"""
Luna V3 Momentum Engine.

Calculates conversation momentum (0-100) based on:
- Message content intensity
- Session duration
- Historical engagement
- Time-based decay

Replaces the V7 TransitionManager with a smoother, momentum-based approach.
"""

import re
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Time-based decay constants
DECAY_PER_MINUTE = 5.0       # Perd 5 points par minute d'inactivité
POST_AFTERCARE_DECAY = 30.0  # Decay agressif après aftercare terminé
SFW_ACCELERATED_DECAY = 10.0 # Decay accéléré sur messages SFW post-session


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
# ATTENTION: Éviter les mots trop génériques (lit, chaud, corps, peau, bouche)
# qui matchent des contextes innocents (météo, anatomie, etc.)
HOT_KEYWORDS = [
    'envie de toi', 'te veux', 'tellement envie',
    'nu', 'nue', 'déshabille', 'string', 'culotte',
    'excité', 'excitée', 'caresser', 'caresse',
    'enleve', 'enlève', 'retire', 'désape',
]

HOT_PATTERNS = [
    r'j\'ai (?:tellement |trop |)envie de toi',
    r'j\'ai envie de (?:toi|te)',
    r'je (?:te |)veux (?:tellement|trop|maintenant)',
    r'si (?:tu étais|t\'étais) là',
    r'dans (?:mon |ton )lit',
    r'(?:tes |mes )mains sur (?:moi|toi|mon|ton)',
    r'(?:ton |mon )corps (?:contre|sur|près)',
    r'(?:ta |ma )peau (?:contre|sur|douce)',
    r'j\'ai (?:trop |tellement |)chaud (?:là|maintenant|avec toi)',
    r'(?:te |)toucher (?:partout|là)',
    r'(?:t\'|te )embrasser',
]

# FLIRT: Light flirting, romantic interest
# Note: "manque" retiré car trop générique ("il me manque de l'argent")
FLIRT_KEYWORDS = [
    'mignon', 'mignonne', 'belle', 'beau', 'canon', 'craquant', 'craquante',
    'pense à toi', 'tu me manques', 'rêvé de toi',
    'adorable', 'sexy', 'attiré', 'attirée', 't\'aime bien',
    'hâte de te voir', 'bisou', 'bisous', 'câlin'
]

FLIRT_PATTERNS = [
    r'tu me manques',
    r'je pense à toi',
    r't\'es (?:trop |vraiment |)(?:mignon|mignonne|beau|belle|canon)',
    r'j\'(?:aime|adore) (?:bien |trop |)(?:parler avec toi|te parler|discuter avec toi)',
    r'(?:gros |plein de |)bisous?',
]

# Negative emotions: Block escalation
# Doit être vérifié AVANT les autres patterns (priorité haute)
NEGATIVE_PATTERNS = [
    # États émotionnels directs
    r'je (?:suis |me sens )(?:triste|mal|déprimée?|seule?|anxieux|anxieuse|pas bien|nulle?|vidée?)',
    r'je (?:vais |)(?:pas bien|mal)',
    r'ça (?:va |)(?:pas|plus)',

    # Dépression / désespoir
    r'j\'ai (?:envie de |)(?:pleurer|mourir|disparaître)',
    r'personne (?:ne |)(?:m\'aime|me comprend)',
    r'j\'en (?:peux |ai )plus',
    r'j\'ai pas envie',
    r'(?:ça|c\'est) (?:pas |)la peine',
    r'à quoi (?:ça |)sert',
    r'je (?:sers|vaux) (?:à |)rien',

    # Anxiété / stress
    r'j\'ai peur',
    r'(?:je suis |j\'suis |jsuis )(?:stressée?|angoissée?|paniquée?)',
    r'j\'angoisse',
    r'ça m\'angoisse',

    # Mal-être général
    r'j\'en ai marre',
    r'ça me (?:fait chier|saoule|gonfle)',
    r'c\'est (?:trop |)(?:dur|difficile|compliqué)',
    r'je (?:supporte|comprends) (?:plus|pas)',
    r'(?:je |j\')(?:me |)(?:déteste|hais)',
]

# Climax indicators (user messages)
CLIMAX_USER_PATTERNS = [
    r'je (?:vais |)jouir',
    r'je jouis',
    r'j\'ai joui',
    r'(?:je|j) (?:viens|vais venir)',
    r'c\'est trop bon',
    r'orgasm',
    r'(?:oui\s*){3,}',  # oui oui oui...
    r'[ao]h{2,}',  # ahhh, ohhh (prolonged sounds, NOT "ahahaha" laughter)
    r'm{2,}h',  # mmmh
    r'💦',
]

# Climax indicators (Luna's responses)
CLIMAX_LUNA_PATTERNS = [
    r'je (?:vais |)jouir',
    r'je jouis',
    r'j\'(?:en |)peux plus',
    r'c\'était (?:trop |tellement |)(?:bon|intense|incroyable)',
    r'oh mon dieu',
    r'wow\.\.\.',
    r'[ao]h{2,}',  # ahhh, ohhh (NOT "ahahaha" laughter)
    r'm{2,}h',  # mmmh
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

    def apply_time_decay(
        self,
        current_momentum: float,
        last_message_at: datetime | None,
        messages_since_climax: int = 999
    ) -> float:
        """
        Apply time-based decay to momentum.

        Args:
            current_momentum: Current momentum value
            last_message_at: Timestamp of last message
            messages_since_climax: Messages since climax for post-aftercare decay

        Returns:
            Decayed momentum value
        """
        if not last_message_at or current_momentum <= 0:
            return current_momentum

        # Calculate elapsed time
        now = datetime.now(timezone.utc)
        if last_message_at.tzinfo is None:
            last_message_at = last_message_at.replace(tzinfo=timezone.utc)

        elapsed_seconds = (now - last_message_at).total_seconds()
        elapsed_minutes = elapsed_seconds / 60

        # Base decay: 5 points per minute
        decay = elapsed_minutes * DECAY_PER_MINUTE

        # Post-aftercare aggressive decay (aftercare = 5 msgs, so 6+ = post)
        if 6 <= messages_since_climax <= 10:
            decay += POST_AFTERCARE_DECAY
            logger.info(f"Post-aftercare decay applied: +{POST_AFTERCARE_DECAY}")

        new_momentum = max(0, current_momentum - decay)

        if decay > 0:
            logger.info(
                f"Time decay: {current_momentum:.1f} → {new_momentum:.1f} "
                f"(elapsed={elapsed_minutes:.1f}min, decay={decay:.1f})"
            )

        return new_momentum

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

    def detect_climax_user(self, message: str) -> bool:
        """Detect if user message indicates climax."""
        msg_lower = message.lower()
        return any(re.search(p, msg_lower) for p in CLIMAX_USER_PATTERNS)

    def detect_climax_luna(self, response: str) -> bool:
        """Detect if Luna's response indicates climax happened."""
        resp_lower = response.lower()
        return any(re.search(p, resp_lower) for p in CLIMAX_LUNA_PATTERNS)

    def detect_climax(self, message: str) -> bool:
        """Detect if message indicates climax (user or Luna)."""
        return self.detect_climax_user(message) or self.detect_climax_luna(message)

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

    def get_nsfw_state(
        self,
        momentum: float,
        messages_since_climax: int = 999
    ) -> str:
        """
        Get NSFW state for prompt selection.

        States:
        - 'sfw': momentum < 30 (use SFW prompt)
        - 'tension': momentum 30-50 (flirt suggestif)
        - 'buildup': momentum 51-70 (intensité croissante)
        - 'climax': momentum 71+ (intense et émotionnel)
        - 'aftercare': post-climax (5 messages)
        - 'post_session': transition retour SFW (6-10 messages post-climax)

        Returns:
            State string for prompt selection
        """
        # Priority 1: Aftercare (5 messages post-climax)
        if messages_since_climax <= 5:
            logger.info(f"NSFW state: aftercare (messages_since_climax={messages_since_climax})")
            return 'aftercare'

        # Priority 2: Post-session transition (6-10 messages post-climax)
        if 6 <= messages_since_climax <= 10:
            logger.info(f"NSFW state: post_session (messages_since_climax={messages_since_climax})")
            return 'post_session'

        # Otherwise, based on momentum
        if momentum >= 70:
            state = 'climax'
        elif momentum >= 50:
            state = 'buildup'
        elif momentum >= 30:
            state = 'tension'
        else:
            state = 'sfw'

        logger.info(f"NSFW state: {state} (momentum={momentum:.1f})")
        return state

    def get_sfw_decay_boost(
        self,
        intensity: Intensity,
        messages_since_climax: int
    ) -> float:
        """
        Get additional decay for SFW messages after NSFW session.

        Returns extra decay to apply when user sends SFW messages
        after an intimate session.
        """
        # Only apply boost if we're in post-session phase (6-15 msgs after climax)
        if messages_since_climax < 6 or messages_since_climax > 15:
            return 0.0

        # SFW message = accelerated return to normal
        if intensity == Intensity.SFW:
            logger.info(f"SFW decay boost: +{SFW_ACCELERATED_DECAY}")
            return SFW_ACCELERATED_DECAY

        return 0.0


# Singleton instance
momentum_engine = MomentumEngine()
