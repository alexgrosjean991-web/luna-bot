"""
Realistic Delays Service - Délais qui cassent l'illusion du bot
Une vraie personne ne répond pas en 3s à chaque message.
"""

import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ResponsePattern(Enum):
    """Patterns de réponse"""
    INSTANT = "instant"           # <5s - elle attendait son message
    QUICK = "quick"               # 5-15s - réponse normale
    NORMAL = "normal"             # 15-45s - elle fait autre chose
    SLOW = "slow"                 # 45s-2min - occupée
    VERY_SLOW = "very_slow"       # 2-5min - vraiment occupée
    DELAYED = "delayed"           # 5-15min - elle répond plus tard


class TypingPattern(Enum):
    """Patterns de frappe"""
    SIMPLE = "simple"             # Tape et envoie
    HESITANT = "hesitant"         # Tape, pause, tape
    REWRITE = "rewrite"           # Tape longtemps, message court (a effacé)
    EXCITED = "excited"           # Tape vite, plusieurs messages
    THINKING = "thinking"         # Long typing, elle réfléchit


@dataclass
class DelayResult:
    """Résultat du calcul de délai"""
    initial_delay: float          # Délai avant de commencer à taper
    typing_duration: float        # Durée du "typing..."
    between_messages: float       # Délai entre messages si split
    pattern: ResponsePattern
    typing_pattern: TypingPattern
    should_split: bool            # Splitter en plusieurs messages?
    split_count: int              # Nombre de messages
    add_excuse: bool              # Ajouter une excuse ("dsl j'étais...")
    excuse_text: Optional[str]    # Texte de l'excuse


# Excuses pour délais longs (FR)
EXCUSES_FR = [
    "dsl j'étais sous la douche",
    "pardon je bossais",
    "désolée j'étais au tel avec ma mère",
    "sorry j'avais pas vu",
    "oops j'étais sur Netflix mdr",
    "dsl Léa me parlait",
    "pardon j'étais dehors",
    "j'avais plus de batterie",
    "désolée j'étais occupée",
    "sorry j'ai pas entendu le notif",
]

# Excuses EN
EXCUSES_EN = [
    "sorry was in the shower",
    "sorry was working",
    "sorry was on the phone with my mom",
    "sorry didnt see it",
    "oops was watching Netflix lol",
    "sorry Sarah was talking to me",
    "sorry was outside",
    "my phone died",
    "sorry was busy",
    "sorry didnt hear the notification",
]


class RealisticDelayService:
    """Service de délais réalistes"""

    def __init__(self):
        self._last_response_time: dict = {}  # user_id -> datetime
        self._consecutive_quick: dict = {}   # user_id -> count

    def calculate_delay(
        self,
        user_id: int,
        user_message: str,
        response: str,
        affection: float,
        hour: int,
        mood: str,
        is_converted: bool,
        is_french: bool,
        is_nsfw: bool = False  # NEW: Mode sexting = réponses rapides
    ) -> DelayResult:
        """
        Calcule le délai réaliste pour une réponse.

        Facteurs:
        - Heure de la journée
        - Mood de Luna
        - Longueur du message user
        - Affection
        - Historique récent (éviter patterns répétitifs)
        - Mode NSFW/sexting (réponses plus rapides)
        """

        # Determine base pattern
        pattern = self._determine_pattern(
            user_id, user_message, affection, hour, mood, is_converted, is_nsfw
        )

        # Calculate delays based on pattern
        initial_delay, typing_duration = self._calculate_delays(
            pattern, user_message, response, hour
        )

        # Determine typing pattern
        typing_pattern = self._determine_typing_pattern(
            response, affection, mood
        )

        # Should we split into multiple messages?
        should_split, split_count, between_delay = self._determine_split(
            response, affection, mood, typing_pattern
        )

        # Add excuse for slow responses? (NEVER during NSFW/sexting)
        add_excuse, excuse_text = self._determine_excuse(
            pattern, is_french, is_nsfw
        )

        # Track this response
        self._track_response(user_id, pattern)

        return DelayResult(
            initial_delay=initial_delay,
            typing_duration=typing_duration,
            between_messages=between_delay,
            pattern=pattern,
            typing_pattern=typing_pattern,
            should_split=should_split,
            split_count=split_count,
            add_excuse=add_excuse,
            excuse_text=excuse_text
        )

    def _determine_pattern(
        self,
        user_id: int,
        user_message: str,
        affection: float,
        hour: int,
        mood: str,
        is_converted: bool,
        is_nsfw: bool = False
    ) -> ResponsePattern:
        """Détermine le pattern de réponse"""

        # === MODE SEXTING/HOT = RÉPONSES RAPIDES ===
        # Quand c'est chaud, elle répond vite - elle est excitée!
        if is_nsfw and affection >= 50:
            logger.debug("🔥 NSFW mode: fast responses enabled")
            r = random.random()
            if r < 0.50:  # 50% instant
                return ResponsePattern.INSTANT
            elif r < 0.85:  # 35% quick
                return ResponsePattern.QUICK
            else:  # 15% normal (pas trop prévisible)
                return ResponsePattern.NORMAL

        # Éviter trop de réponses rapides consécutives (sauf NSFW)
        consecutive = self._consecutive_quick.get(user_id, 0)
        if consecutive >= 3:
            # Force un délai plus long
            return random.choice([ResponsePattern.NORMAL, ResponsePattern.SLOW])

        # === FACTEURS TEMPORELS ===

        # Matin (7h-11h) - Luna est lente
        if 7 <= hour < 11:
            base_weights = {
                ResponsePattern.INSTANT: 0.05,
                ResponsePattern.QUICK: 0.15,
                ResponsePattern.NORMAL: 0.35,
                ResponsePattern.SLOW: 0.30,
                ResponsePattern.VERY_SLOW: 0.10,
                ResponsePattern.DELAYED: 0.05,
            }

        # Après-midi (11h-17h) - Meilleur mood
        elif 11 <= hour < 17:
            base_weights = {
                ResponsePattern.INSTANT: 0.15,
                ResponsePattern.QUICK: 0.35,
                ResponsePattern.NORMAL: 0.30,
                ResponsePattern.SLOW: 0.15,
                ResponsePattern.VERY_SLOW: 0.04,
                ResponsePattern.DELAYED: 0.01,
            }

        # Soir (17h-22h) - Relaxed
        elif 17 <= hour < 22:
            base_weights = {
                ResponsePattern.INSTANT: 0.20,
                ResponsePattern.QUICK: 0.40,
                ResponsePattern.NORMAL: 0.25,
                ResponsePattern.SLOW: 0.10,
                ResponsePattern.VERY_SLOW: 0.04,
                ResponsePattern.DELAYED: 0.01,
            }

        # Nuit (22h-7h) - Variable
        else:
            base_weights = {
                ResponsePattern.INSTANT: 0.10,
                ResponsePattern.QUICK: 0.25,
                ResponsePattern.NORMAL: 0.30,
                ResponsePattern.SLOW: 0.20,
                ResponsePattern.VERY_SLOW: 0.10,
                ResponsePattern.DELAYED: 0.05,
            }

        # === MODIFICATEURS ===

        weights = base_weights.copy()

        # Affection haute = répond plus vite
        if affection > 70:
            weights[ResponsePattern.INSTANT] *= 1.5
            weights[ResponsePattern.QUICK] *= 1.3
            weights[ResponsePattern.SLOW] *= 0.5
            weights[ResponsePattern.VERY_SLOW] *= 0.3

        # Affection basse = répond plus lentement
        elif affection < 30:
            weights[ResponsePattern.INSTANT] *= 0.3
            weights[ResponsePattern.QUICK] *= 0.5
            weights[ResponsePattern.SLOW] *= 1.5
            weights[ResponsePattern.VERY_SLOW] *= 1.5

        # Converted = plus disponible
        if is_converted:
            weights[ResponsePattern.INSTANT] *= 1.3
            weights[ResponsePattern.QUICK] *= 1.2
            weights[ResponsePattern.DELAYED] *= 0.3

        # Message court de l'user = réponse plus rapide
        if len(user_message) < 20:
            weights[ResponsePattern.QUICK] *= 1.2

        # Message long = elle prend le temps de lire
        elif len(user_message) > 150:
            weights[ResponsePattern.NORMAL] *= 1.3
            weights[ResponsePattern.SLOW] *= 1.2

        # Question directe = répond plus vite
        if "?" in user_message:
            weights[ResponsePattern.INSTANT] *= 1.2
            weights[ResponsePattern.QUICK] *= 1.2

        # Mood effects
        if mood == "excited" or mood == "flirty":
            weights[ResponsePattern.INSTANT] *= 1.4
            weights[ResponsePattern.QUICK] *= 1.3
        elif mood == "tired":
            weights[ResponsePattern.SLOW] *= 1.5
            weights[ResponsePattern.VERY_SLOW] *= 1.3
        elif mood == "sad":
            weights[ResponsePattern.NORMAL] *= 1.2
            weights[ResponsePattern.SLOW] *= 1.2

        # Normalize weights
        total = sum(weights.values())
        weights = {k: v/total for k, v in weights.items()}

        # Random selection
        r = random.random()
        cumulative = 0
        for pattern, weight in weights.items():
            cumulative += weight
            if r <= cumulative:
                return pattern

        return ResponsePattern.NORMAL

    def _calculate_delays(
        self,
        pattern: ResponsePattern,
        user_message: str,
        response: str,
        hour: int
    ) -> Tuple[float, float]:
        """Calcule les délais en secondes"""

        # Base delays par pattern
        delays = {
            ResponsePattern.INSTANT: (0.5, 3.0, 2.0, 5.0),    # initial_min, initial_max, typing_min, typing_max
            ResponsePattern.QUICK: (2.0, 8.0, 3.0, 8.0),
            ResponsePattern.NORMAL: (8.0, 25.0, 5.0, 15.0),
            ResponsePattern.SLOW: (30.0, 90.0, 8.0, 20.0),
            ResponsePattern.VERY_SLOW: (120.0, 300.0, 10.0, 25.0),
            ResponsePattern.DELAYED: (300.0, 900.0, 5.0, 15.0),
        }

        init_min, init_max, type_min, type_max = delays[pattern]

        # Initial delay
        initial_delay = random.uniform(init_min, init_max)

        # Typing duration based on response length
        words = len(response.split())
        base_typing = random.uniform(type_min, type_max)

        # ~3-5 chars per second typing speed (with thinking)
        chars_per_second = random.uniform(3, 5)
        content_typing = len(response) / chars_per_second

        typing_duration = min(base_typing + content_typing * 0.3, 30)  # Cap at 30s

        # Night time = slower typing
        if hour >= 23 or hour < 7:
            typing_duration *= 1.3
            initial_delay *= 1.2

        return initial_delay, typing_duration

    def _determine_typing_pattern(
        self,
        response: str,
        affection: float,
        mood: str
    ) -> TypingPattern:
        """Détermine le pattern de frappe"""

        r = random.random()

        # Excited mood = excited typing
        if mood in ["excited", "flirty"] and affection > 50:
            if r < 0.4:
                return TypingPattern.EXCITED

        # Message court après long typing = rewrite
        if len(response) < 50 and r < 0.15:
            return TypingPattern.REWRITE

        # Hesitant parfois
        if r < 0.2:
            return TypingPattern.HESITANT

        # Thinking pour messages longs
        if len(response) > 150 and r < 0.3:
            return TypingPattern.THINKING

        return TypingPattern.SIMPLE

    def _determine_split(
        self,
        response: str,
        affection: float,
        mood: str,
        typing_pattern: TypingPattern
    ) -> Tuple[bool, int, float]:
        """Détermine si on split en plusieurs messages"""

        # Excited = plus de split
        if typing_pattern == TypingPattern.EXCITED:
            if random.random() < 0.6:
                return True, random.randint(2, 3), random.uniform(1.0, 3.0)

        # Long response = maybe split
        if len(response) > 100:
            if random.random() < 0.35:
                return True, 2, random.uniform(2.0, 5.0)

        # High affection = double text sometimes
        if affection > 60 and random.random() < 0.2:
            return True, 2, random.uniform(1.5, 4.0)

        return False, 1, 0

    def _determine_excuse(
        self,
        pattern: ResponsePattern,
        is_french: bool,
        is_nsfw: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Détermine si on ajoute une excuse pour le délai"""

        # === JAMAIS D'EXCUSE PENDANT LE SEXTING ===
        # "j'étais sur Netflix" pendant un moment hot = immersion cassée
        if is_nsfw:
            return False, None

        if pattern in [ResponsePattern.VERY_SLOW, ResponsePattern.DELAYED]:
            if random.random() < 0.7:  # 70% chance
                excuses = EXCUSES_FR if is_french else EXCUSES_EN
                return True, random.choice(excuses)

        if pattern == ResponsePattern.SLOW:
            if random.random() < 0.3:  # 30% chance
                excuses = EXCUSES_FR if is_french else EXCUSES_EN
                return True, random.choice(excuses)

        return False, None

    def _track_response(self, user_id: int, pattern: ResponsePattern):
        """Track les réponses pour éviter patterns répétitifs"""

        now = datetime.now(timezone.utc)
        self._last_response_time[user_id] = now

        if pattern in [ResponsePattern.INSTANT, ResponsePattern.QUICK]:
            self._consecutive_quick[user_id] = self._consecutive_quick.get(user_id, 0) + 1
        else:
            self._consecutive_quick[user_id] = 0


class TypingSimulator:
    """Simule le typing indicator de manière réaliste"""

    @staticmethod
    async def simulate_typing(
        context,
        chat_id: int,
        delay_result: DelayResult
    ):
        """
        Simule le typing de manière réaliste.

        Patterns:
        - SIMPLE: typing continu
        - HESITANT: typing, pause, typing
        - REWRITE: long typing puis envoi rapide
        - EXCITED: typing rapide
        - THINKING: typing avec pauses
        """

        from telegram.constants import ChatAction

        pattern = delay_result.typing_pattern
        typing_duration = delay_result.typing_duration

        if pattern == TypingPattern.SIMPLE:
            # Typing continu avec refresh
            elapsed = 0
            while elapsed < typing_duration:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                wait = min(4.5, typing_duration - elapsed)  # Refresh every 4.5s
                await asyncio.sleep(wait)
                elapsed += wait

        elif pattern == TypingPattern.HESITANT:
            # Typing, pause, typing
            first_part = typing_duration * 0.4
            pause = random.uniform(2, 5)
            second_part = typing_duration * 0.4

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(first_part)
            # Pause (no typing)
            await asyncio.sleep(pause)
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(second_part)

        elif pattern == TypingPattern.REWRITE:
            # Long typing (elle efface et réécrit)
            long_duration = typing_duration * 1.5

            elapsed = 0
            while elapsed < long_duration:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                wait = min(4.5, long_duration - elapsed)
                await asyncio.sleep(wait)
                elapsed += wait

        elif pattern == TypingPattern.EXCITED:
            # Typing rapide
            fast_duration = typing_duration * 0.6

            elapsed = 0
            while elapsed < fast_duration:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                wait = min(3, fast_duration - elapsed)
                await asyncio.sleep(wait)
                elapsed += wait

        elif pattern == TypingPattern.THINKING:
            # Typing avec pauses (elle réfléchit)
            segments = 3
            segment_duration = typing_duration / segments

            for i in range(segments):
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(segment_duration * 0.7)
                if i < segments - 1:
                    await asyncio.sleep(random.uniform(1, 3))  # Pause

        else:
            # Default
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(typing_duration)


def split_message_naturally(response: str, count: int = 2) -> List[str]:
    """Split un message de manière naturelle"""

    if count == 1 or len(response) < 50:
        return [response]

    # Try to split on sentence boundaries
    import re
    sentences = re.split(r'(?<=[.!?])\s+', response)

    if len(sentences) >= count:
        # Distribute sentences
        per_part = len(sentences) // count
        parts = []
        for i in range(count):
            start = i * per_part
            end = start + per_part if i < count - 1 else len(sentences)
            parts.append(' '.join(sentences[start:end]))
        return [p for p in parts if p.strip()]

    # Fall back to rough split
    mid = len(response) // 2
    # Find nearest space
    space_pos = response.find(' ', mid)
    if space_pos == -1:
        space_pos = mid

    return [response[:space_pos].strip(), response[space_pos:].strip()]


# Instance globale
delay_service = RealisticDelayService()
typing_simulator = TypingSimulator()
