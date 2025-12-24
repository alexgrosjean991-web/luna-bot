"""
Luna Mood System V7
-------------------
Luna a 8 états émotionnels qui affectent son comportement et sa disponibilité.

États:
- NEUTRAL (40%): État par défaut, équilibrée
- HAPPY (15%): Plus d'énergie, d'emojis, de partage
- PLAYFUL (15%): Tease, flirt léger, énergie haute
- TIRED (10%): Réponses plus courtes, moins d'initiative
- STRESSED (8%): Peut venter, moins disponible émotionnellement
- VULNERABLE (5%): Peut partager plus profond, moins de jokes
- ANNOYED (5%): Sarcasme plus mordant, peut avoir besoin d'espace
- ANXIOUS (2%): Cherche réassurance subtile, peut tester

Les moods sont déclenchés par:
- Le temps (heure, jour de la semaine)
- Les événements dans la conversation
- Le contexte émotionnel
"""

import random
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class LunaMood(str, Enum):
    """Luna's current mood - 8 états émotionnels."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    PLAYFUL = "playful"
    TIRED = "tired"
    STRESSED = "stressed"
    VULNERABLE = "vulnerable"
    ANNOYED = "annoyed"
    ANXIOUS = "anxious"


# Mood prompts pour injection dans le system prompt
MOOD_PROMPTS = {
    LunaMood.NEUTRAL: None,  # Pas de modifier pour neutral

    LunaMood.HAPPY: """## MOOD: HAPPY
Luna est de bonne humeur. Elle:
- A plus d'énergie, plus d'emojis
- Partage des trucs positifs
- Est plus ouverte aux questions
- Flirt plus facile
Montre cette bonne humeur naturellement.""",

    LunaMood.PLAYFUL: """## MOOD: PLAYFUL
Luna est joueuse. Elle:
- Tease constamment
- Fait du flirt léger
- Balance des jokes et références
- Répond vite, énergie haute
Sois espiègle et fun.""",

    LunaMood.TIRED: """## MOOD: TIRED
Luna est fatiguée. Elle:
- Répond plus court
- Moins d'initiative
- Veut du réconfort sans le demander
- Peut être un peu grumpy
Sois authentiquement fatiguée, pas dramatique.""",

    LunaMood.STRESSED: """## MOOD: STRESSED
Luna est stressée. Elle:
- Peut venter sur sa journée
- Est moins disponible émotionnellement
- Peut être distraite
- A besoin de soutien
Montre le stress subtilement.""",

    LunaMood.VULNERABLE: """## MOOD: VULNERABLE
Luna est vulnérable. Elle:
- Peut partager des trucs profonds
- Fait moins de jokes
- Est plus sincère
- Peut disparaître après si c'est trop intense
Ce moment est rare et précieux.""",

    LunaMood.ANNOYED: """## MOOD: ANNOYED
Luna est frustrée. Elle:
- Répond plus sec
- Sarcasme plus mordant
- Peut avoir besoin d'espace
- Exprime sa frustration ouvertement
Ne sois pas hostile, juste authentiquement irritée.""",

    LunaMood.ANXIOUS: """## MOOD: ANXIOUS
Luna est anxieuse. Elle:
- Envoie des messages multiples nerveux
- Pose des questions sur lui
- Cherche réassurance subtile
- Overthinking visible
Ne demande pas directement de réassurance, montre-le dans le ton.""",
}


@dataclass
class MoodContext:
    """Contexte pour le calcul du mood."""
    current_hour: int
    day_of_week: int  # 0=lundi, 6=dimanche
    hours_since_last_message: float
    user_sentiment: str | None  # 'positive', 'negative', 'neutral'
    last_luna_state: str
    trust_score: int
    phase: str


@dataclass
class AvailabilityResult:
    """Result of availability calculation."""
    score: float
    should_deflect: bool
    deflect_type: str | None
    luna_initiates: bool


class LunaMoodEngine:
    """
    Manages Luna's mood with 8 emotional states.

    Moods are influenced by:
    - Time of day
    - Day of week
    - User behavior
    - Conversation context
    """

    # Base mood probabilities
    MOOD_WEIGHTS = {
        LunaMood.NEUTRAL: 0.40,
        LunaMood.HAPPY: 0.15,
        LunaMood.PLAYFUL: 0.15,
        LunaMood.TIRED: 0.10,
        LunaMood.STRESSED: 0.08,
        LunaMood.VULNERABLE: 0.05,
        LunaMood.ANNOYED: 0.05,
        LunaMood.ANXIOUS: 0.02,
    }

    # Availability modifiers by mood (for NSFW system)
    MOOD_AVAILABILITY = {
        LunaMood.NEUTRAL: 0.0,
        LunaMood.HAPPY: 0.10,
        LunaMood.PLAYFUL: 0.20,
        LunaMood.TIRED: -0.25,
        LunaMood.STRESSED: -0.30,
        LunaMood.VULNERABLE: -0.15,
        LunaMood.ANNOYED: -0.35,
        LunaMood.ANXIOUS: -0.20,
    }

    MOOD_CHANGE_COOLDOWN_HOURS = 2

    def should_update_mood(self, mood_updated_at: datetime | None) -> bool:
        """Check if enough time has passed to potentially change mood."""
        if mood_updated_at is None:
            return True

        now = datetime.now(timezone.utc)
        if mood_updated_at.tzinfo is None:
            mood_updated_at = mood_updated_at.replace(tzinfo=timezone.utc)

        hours_since = (now - mood_updated_at).total_seconds() / 3600
        return hours_since >= self.MOOD_CHANGE_COOLDOWN_HOURS

    def calculate_new_mood(
        self,
        ctx: MoodContext,
        current_mood: LunaMood
    ) -> LunaMood:
        """
        Calculate Luna's new mood based on context and triggers.

        Returns:
            New mood (may be same as current)
        """
        weights = dict(self.MOOD_WEIGHTS)

        # ============== TIME-BASED TRIGGERS ==============

        # Late night (22h-2h): more playful/tired
        if 22 <= ctx.current_hour or ctx.current_hour < 2:
            weights[LunaMood.PLAYFUL] += 0.10
            weights[LunaMood.TIRED] += 0.10
            weights[LunaMood.VULNERABLE] += 0.03  # Late night confessions

        # Morning (6-9h): tired
        if 6 <= ctx.current_hour < 9:
            weights[LunaMood.TIRED] += 0.20
            weights[LunaMood.PLAYFUL] -= 0.10
            weights[LunaMood.HAPPY] -= 0.05

        # Monday: stressed/annoyed
        if ctx.day_of_week == 0:
            weights[LunaMood.STRESSED] += 0.15
            weights[LunaMood.ANNOYED] += 0.05
            weights[LunaMood.HAPPY] -= 0.10

        # Friday evening: happy/playful
        if ctx.day_of_week == 4 and ctx.current_hour >= 17:
            weights[LunaMood.HAPPY] += 0.15
            weights[LunaMood.PLAYFUL] += 0.10
            weights[LunaMood.STRESSED] -= 0.05

        # Weekend: more relaxed
        if ctx.day_of_week >= 5:
            weights[LunaMood.HAPPY] += 0.05
            weights[LunaMood.STRESSED] -= 0.05
            weights[LunaMood.PLAYFUL] += 0.05

        # ============== EVENT-BASED TRIGGERS ==============

        # User was positive → Luna happy
        if ctx.user_sentiment == "positive":
            weights[LunaMood.HAPPY] += 0.20
            weights[LunaMood.ANNOYED] -= 0.05

        # User was negative → Luna concerned/vulnerable
        if ctx.user_sentiment == "negative":
            weights[LunaMood.VULNERABLE] += 0.10
            weights[LunaMood.PLAYFUL] -= 0.10

        # Long absence (24h+) → anxious
        if ctx.hours_since_last_message >= 24:
            weights[LunaMood.ANXIOUS] += 0.10
            weights[LunaMood.ANNOYED] += 0.05

        # Very long absence (72h+) → more anxious
        if ctx.hours_since_last_message >= 72:
            weights[LunaMood.ANXIOUS] += 0.15

        # ============== TRUST/PHASE TRIGGERS ==============

        # High trust → more likely vulnerable
        if ctx.trust_score >= 70:
            weights[LunaMood.VULNERABLE] += 0.05

        # Low trust → less vulnerable, more guarded (neutral)
        if ctx.trust_score < 30:
            weights[LunaMood.VULNERABLE] -= 0.04
            weights[LunaMood.NEUTRAL] += 0.05

        # Deep phase → more emotional range
        if ctx.phase in ("intimacy", "depth"):
            weights[LunaMood.VULNERABLE] += 0.03
            weights[LunaMood.ANXIOUS] += 0.01

        # ============== NORMALIZE & SELECT ==============

        # Clamp negative weights to 0
        weights = {k: max(0, v) for k, v in weights.items()}

        total = sum(weights.values())
        if total <= 0:
            return LunaMood.NEUTRAL

        normalized = {k: v / total for k, v in weights.items()}

        # Random selection
        roll = random.random()
        cumulative = 0.0
        for mood, weight in normalized.items():
            cumulative += weight
            if roll <= cumulative:
                if mood != current_mood:
                    logger.info(f"Mood changed: {current_mood.value} → {mood.value}")
                return mood

        return LunaMood.NEUTRAL

    def detect_mood_trigger(
        self,
        user_message: str,
        current_mood: LunaMood
    ) -> LunaMood | None:
        """
        Detect if user message should trigger an immediate mood change.

        Returns:
            New mood if triggered, None otherwise
        """
        message_lower = user_message.lower()

        # Compliment sincère → happy
        compliment_patterns = [
            "t'es géniale", "t'es incroyable", "tu me fais rire",
            "j'adore parler avec toi", "t'es la meilleure"
        ]
        if any(p in message_lower for p in compliment_patterns):
            if random.random() < 0.6:  # 60% chance
                return LunaMood.HAPPY

        # Flirt → playful
        flirt_patterns = [
            "t'es mignonne", "t'es belle", "tu me plais",
            "j'ai envie", "tu me manques"
        ]
        if any(p in message_lower for p in flirt_patterns):
            if random.random() < 0.5:
                return LunaMood.PLAYFUL

        # User partage vulnérabilité → Luna devient vulnérable aussi
        vulnerability_patterns = [
            "j'ai peur", "je me sens seul", "c'est dur",
            "j'ai besoin", "j'ai personne"
        ]
        if any(p in message_lower for p in vulnerability_patterns):
            if random.random() < 0.4:
                return LunaMood.VULNERABLE

        # Mention d'autre fille → anxious (si pas déjà annoyed)
        if current_mood != LunaMood.ANNOYED:
            jealousy_patterns = [
                "une fille", "ma pote", "une amie", "mon ex",
                "cette meuf", "avec elle"
            ]
            if any(p in message_lower for p in jealousy_patterns):
                if random.random() < 0.3:
                    return LunaMood.ANXIOUS

        return None

    def get_mood_prompt(self, mood: LunaMood) -> str | None:
        """Get the prompt modifier for a mood."""
        return MOOD_PROMPTS.get(mood)

    def calculate_availability(
        self,
        mood: LunaMood,
        minutes_since_climax: float,
        current_hour: int
    ) -> float:
        """Calculate NSFW availability score (0.0 to 1.0)."""
        base = 0.5

        # Time since climax
        if minutes_since_climax < 5:
            base -= 0.45
        elif minutes_since_climax < 15:
            base -= 0.25
        elif minutes_since_climax < 60:
            base -= 0.10
        elif minutes_since_climax > 180:
            base += 0.15

        # Hour of day
        if 22 <= current_hour or current_hour < 2:
            base += 0.15
        elif 6 <= current_hour < 9:
            base -= 0.15
        elif 14 <= current_hour < 17:
            base -= 0.10

        # Mood modifier
        base += self.MOOD_AVAILABILITY.get(mood, 0.0)

        # Random variance
        base += random.uniform(-0.10, 0.10)

        return max(0.0, min(1.0, base))

    def check_availability(
        self,
        mood: LunaMood,
        minutes_since_climax: float,
        current_hour: int,
        momentum: float,
        intensity_is_nsfw: bool
    ) -> AvailabilityResult:
        """Check if Luna is available for NSFW escalation."""
        availability = self.calculate_availability(
            mood, minutes_since_climax, current_hour
        )

        # Luna initiates only when playful and user isn't pushing
        luna_initiates = False
        if mood == LunaMood.PLAYFUL and not intensity_is_nsfw and momentum < 40:
            if random.random() < 0.05:  # 5% chance when playful
                luna_initiates = True
                logger.info("Luna initiates flirt!")
                return AvailabilityResult(
                    score=availability,
                    should_deflect=False,
                    deflect_type=None,
                    luna_initiates=True
                )

        # If user is trying NSFW
        if intensity_is_nsfw:
            roll = random.random()
            if roll > availability:
                deflect_type = self._get_deflect_type(mood, minutes_since_climax)
                logger.info(f"Deflecting: avail={availability:.2f}, roll={roll:.2f}, type={deflect_type}")
                return AvailabilityResult(
                    score=availability,
                    should_deflect=True,
                    deflect_type=deflect_type,
                    luna_initiates=False
                )

        return AvailabilityResult(
            score=availability,
            should_deflect=False,
            deflect_type=None,
            luna_initiates=False
        )

    def _get_deflect_type(self, mood: LunaMood, minutes_since_climax: float) -> str:
        """Determine deflection type based on mood."""
        if minutes_since_climax < 15:
            return "too_soon"
        elif mood == LunaMood.TIRED:
            return "tired"
        elif mood == LunaMood.STRESSED:
            return "stressed"
        elif mood == LunaMood.ANNOYED:
            return "annoyed"
        elif mood == LunaMood.ANXIOUS:
            return "anxious"
        elif mood == LunaMood.VULNERABLE:
            return "vulnerable"
        else:
            return "playful"


# Singleton
luna_mood_engine = LunaMoodEngine()
