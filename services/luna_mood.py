"""
Luna Mood & NSFW Availability System.

Luna has her own "mood" that affects her availability for NSFW content.
Like a real girlfriend, she's not always in the mood.

Moods:
- playful: More open to advances (+15% availability)
- tired: Gently deflects (-25% availability)
- romantic: Wants connection first (-10% availability)
- horny: SHE initiates - JACKPOT (+40% availability, very rare)
- normal: Standard behavior (baseline)

The user never knows her mood directly - they must "read" her signals.
"""

import random
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class LunaMood(str, Enum):
    """Luna's current mood."""
    PLAYFUL = "playful"
    TIRED = "tired"
    ROMANTIC = "romantic"
    HORNY = "horny"
    NORMAL = "normal"


@dataclass
class AvailabilityResult:
    """Result of availability calculation."""
    score: float           # 0.0 to 1.0
    should_deflect: bool   # True if Luna should deflect
    deflect_type: str | None  # 'tired', 'romantic', 'too_soon', None
    luna_initiates: bool   # True if Luna should initiate (jackpot!)


class LunaMoodEngine:
    """
    Manages Luna's mood and NSFW availability.

    Key principles:
    - Mood changes every 2-4 hours (not every message)
    - 'horny' is VERY rare (max 1x per week per user)
    - Deflections are gentle, never rejections
    - When Luna initiates = massive dopamine hit
    """

    # Mood change probabilities (per check, ~every 2-4 hours)
    MOOD_WEIGHTS = {
        LunaMood.NORMAL: 0.40,
        LunaMood.PLAYFUL: 0.30,
        LunaMood.TIRED: 0.15,
        LunaMood.ROMANTIC: 0.14,
        LunaMood.HORNY: 0.01,  # 1% base - very rare
    }

    # Availability modifiers by mood
    MOOD_AVAILABILITY = {
        LunaMood.PLAYFUL: 0.15,
        LunaMood.TIRED: -0.25,
        LunaMood.ROMANTIC: -0.10,
        LunaMood.HORNY: 0.40,
        LunaMood.NORMAL: 0.0,
    }

    # Minimum hours between mood changes
    MOOD_CHANGE_COOLDOWN_HOURS = 2

    # Minimum days between 'horny' moods
    HORNY_COOLDOWN_DAYS = 5

    def should_update_mood(
        self,
        mood_updated_at: datetime | None
    ) -> bool:
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
        current_mood: LunaMood,
        last_horny_at: datetime | None,
        hours_since_climax: float,
        current_hour: int
    ) -> LunaMood:
        """
        Calculate Luna's new mood based on context.

        Args:
            current_mood: Current mood
            last_horny_at: Last time mood was 'horny'
            hours_since_climax: Hours since last climax
            current_hour: Current hour (0-23)

        Returns:
            New mood (may be same as current)
        """
        weights = dict(self.MOOD_WEIGHTS)

        # Horny cooldown check
        can_be_horny = True
        if last_horny_at:
            now = datetime.now(timezone.utc)
            if last_horny_at.tzinfo is None:
                last_horny_at = last_horny_at.replace(tzinfo=timezone.utc)
            days_since_horny = (now - last_horny_at).total_seconds() / 86400
            if days_since_horny < self.HORNY_COOLDOWN_DAYS:
                can_be_horny = False
                weights[LunaMood.HORNY] = 0.0

        # Time-based adjustments
        if 22 <= current_hour or current_hour < 2:
            # Late night: more likely playful/horny
            weights[LunaMood.PLAYFUL] += 0.10
            if can_be_horny:
                weights[LunaMood.HORNY] += 0.02
            weights[LunaMood.TIRED] += 0.05
        elif 6 <= current_hour < 9:
            # Morning: more tired
            weights[LunaMood.TIRED] += 0.15
            weights[LunaMood.PLAYFUL] -= 0.10
        elif 20 <= current_hour < 22:
            # Evening: more romantic
            weights[LunaMood.ROMANTIC] += 0.10

        # Long time since climax: slightly more likely to be horny
        if can_be_horny and hours_since_climax > 48:
            weights[LunaMood.HORNY] += 0.03
        elif can_be_horny and hours_since_climax > 24:
            weights[LunaMood.HORNY] += 0.01

        # Normalize weights
        total = sum(max(0, w) for w in weights.values())
        if total <= 0:
            return LunaMood.NORMAL

        normalized = {k: max(0, v) / total for k, v in weights.items()}

        # Random selection
        roll = random.random()
        cumulative = 0.0
        for mood, weight in normalized.items():
            cumulative += weight
            if roll <= cumulative:
                logger.info(f"Mood changed: {current_mood.value} → {mood.value}")
                return mood

        return LunaMood.NORMAL

    def calculate_availability(
        self,
        mood: LunaMood,
        minutes_since_climax: float,
        current_hour: int
    ) -> float:
        """
        Calculate NSFW availability score (0.0 to 1.0).

        Higher = more available for NSFW content.
        """
        base = 0.5

        # Time since climax
        if minutes_since_climax < 5:
            base -= 0.45  # Almost impossible
        elif minutes_since_climax < 15:
            base -= 0.25
        elif minutes_since_climax < 60:
            base -= 0.10
        elif minutes_since_climax > 180:
            base += 0.15  # 3h+ bonus

        # Hour of day
        if 22 <= current_hour or current_hour < 2:
            base += 0.15  # Late night bonus
        elif 6 <= current_hour < 9:
            base -= 0.15  # Morning penalty
        elif 14 <= current_hour < 17:
            base -= 0.10  # Work hours penalty

        # Mood modifier
        base += self.MOOD_AVAILABILITY.get(mood, 0.0)

        # Random variance ±10%
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
        """
        Check if Luna is available for NSFW escalation.

        Args:
            mood: Current Luna mood
            minutes_since_climax: Minutes since last climax
            current_hour: Current hour (0-23)
            momentum: Current conversation momentum
            intensity_is_nsfw: True if user message is NSFW

        Returns:
            AvailabilityResult with deflection info
        """
        availability = self.calculate_availability(
            mood, minutes_since_climax, current_hour
        )

        # Check if Luna should initiate (jackpot!)
        luna_initiates = False
        if mood == LunaMood.HORNY and not intensity_is_nsfw and momentum < 40:
            # Luna initiates when SHE's horny and user is NOT being explicit
            if random.random() < 0.3:  # 30% chance when horny
                luna_initiates = True
                logger.info("JACKPOT: Luna initiates!")
                return AvailabilityResult(
                    score=availability,
                    should_deflect=False,
                    deflect_type=None,
                    luna_initiates=True
                )

        # If user is trying to escalate to NSFW (only check on NSFW messages, not high momentum alone)
        # High momentum doesn't mean user is currently trying to escalate
        if intensity_is_nsfw:
            roll = random.random()

            if roll > availability:
                # Deflect based on mood/context
                deflect_type = self._get_deflect_type(
                    mood, minutes_since_climax
                )
                logger.info(
                    f"Deflecting: availability={availability:.2f}, "
                    f"roll={roll:.2f}, type={deflect_type}"
                )
                return AvailabilityResult(
                    score=availability,
                    should_deflect=True,
                    deflect_type=deflect_type,
                    luna_initiates=False
                )

        # Available
        return AvailabilityResult(
            score=availability,
            should_deflect=False,
            deflect_type=None,
            luna_initiates=False
        )

    def _get_deflect_type(
        self,
        mood: LunaMood,
        minutes_since_climax: float
    ) -> str:
        """Determine what type of deflection to use."""
        if minutes_since_climax < 15:
            return "too_soon"
        elif mood == LunaMood.TIRED:
            return "tired"
        elif mood == LunaMood.ROMANTIC:
            return "romantic"
        else:
            return "playful"  # Default gentle deflection


# Singleton
luna_mood_engine = LunaMoodEngine()
