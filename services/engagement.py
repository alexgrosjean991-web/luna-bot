"""
Services - Engagement Engine (V7)

Behavioral mechanics. Le prompt guide, le code exécute.

Research references (code only, NOT in prompts):
- Intermittent Reinforcement (Skinner) → VariableRewards
- Parasocial Relationships → ProactiveEngine
- Push-Pull Dynamics → JealousyHandler
"""

import random
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field

PARIS_TZ = ZoneInfo("Europe/Paris")


# =============================================================================
# VARIABLE REWARDS (Skinner's Intermittent Reinforcement)
# =============================================================================

@dataclass
class RewardState:
    """Tracks reward state per user."""
    last_high_affection_at: Optional[datetime] = None
    messages_since_reward: int = 0
    reward_streak: int = 0  # Consecutive high rewards


class VariableRewards:
    """
    Randomise l'intensité des réponses de Luna.
    Crée l'imprévisibilité qui génère l'addiction.
    """

    # Affection levels with base probabilities
    LEVELS = {
        "low": 0.15,      # Distante, courte
        "medium": 0.55,   # Normale
        "high": 0.25,     # Très affectueuse
        "jackpot": 0.05,  # Rare, intense (tu me manquais tellement...)
    }

    # Response length variance
    LENGTH_VARIANCE = {
        "low": (1, 2),      # 1-2 phrases
        "medium": (2, 3),   # 2-3 phrases
        "high": (3, 4),     # 3-4 phrases
        "jackpot": (4, 5),  # 4-5 phrases
    }

    @classmethod
    def get_affection_level(cls, state: RewardState, phase: str) -> str:
        """
        Détermine le niveau d'affection pour ce message.
        Uses weighted random with anti-streak logic.
        """
        # Prevent too many jackpots in a row
        if state.reward_streak >= 2:
            weights = {"low": 0.30, "medium": 0.60, "high": 0.10, "jackpot": 0.0}
        # Increase jackpot chance after drought
        elif state.messages_since_reward >= 15:
            weights = {"low": 0.05, "medium": 0.40, "high": 0.40, "jackpot": 0.15}
        # Phase modifiers
        elif phase == "HOOK":
            weights = {"low": 0.20, "medium": 0.60, "high": 0.18, "jackpot": 0.02}
        elif phase == "TENSION":
            weights = {"low": 0.25, "medium": 0.45, "high": 0.25, "jackpot": 0.05}
        elif phase == "LIBRE":
            weights = {"low": 0.10, "medium": 0.50, "high": 0.30, "jackpot": 0.10}
        else:
            weights = cls.LEVELS.copy()

        # Weighted random choice
        r = random.random()
        cumulative = 0
        for level, prob in weights.items():
            cumulative += prob
            if r <= cumulative:
                return level
        return "medium"

    @classmethod
    def update_state(cls, state: RewardState, level: str) -> None:
        """Update state after reward given."""
        if level in ("high", "jackpot"):
            state.last_high_affection_at = datetime.now(PARIS_TZ)
            state.messages_since_reward = 0
            state.reward_streak += 1
        else:
            state.messages_since_reward += 1
            state.reward_streak = 0

    @classmethod
    def get_length_range(cls, level: str) -> Tuple[int, int]:
        """Get min/max phrases for this affection level."""
        return cls.LENGTH_VARIANCE.get(level, (2, 3))

    @classmethod
    def get_modifier(cls, level: str) -> str:
        """Get prompt modifier for affection level."""
        modifiers = {
            "low": "Réponds brièvement. 1-2 phrases max. Un peu distante.",
            "medium": "Réponds normalement. 2-3 phrases.",
            "high": "Sois particulièrement affectueuse. 3-4 phrases. Montre que tu tiens à lui.",
            "jackpot": "Tu l'as vraiment manqué. 4-5 phrases. Très affectueuse, émotive. Un message qu'il va relire.",
        }
        return modifiers.get(level, modifiers["medium"])


# =============================================================================
# PHOTO TRIGGERS
# =============================================================================

@dataclass
class PhotoState:
    """Tracks photo state per user."""
    last_photo_at: Optional[datetime] = None
    photos_sent_today: int = 0
    photo_date: Optional[str] = None


class PhotoTriggers:
    """
    Gère quand Luna envoie des photos.
    """

    # Photo types by phase
    TYPES_BY_PHASE = {
        "HOOK": ["pixel"],  # Just cat
        "CONNECT": ["pixel", "selfie_casual"],
        "ATTACH": ["pixel", "selfie_casual", "selfie_cute"],
        "TENSION": ["pixel", "selfie_casual", "selfie_cute", "tease"],
        "LIBRE": ["pixel", "selfie_casual", "selfie_cute", "tease", "nsfw_soft", "nsfw"],
    }

    # Cooldowns in hours
    COOLDOWNS = {
        "pixel": 2,
        "selfie_casual": 6,
        "selfie_cute": 12,
        "tease": 24,
        "nsfw_soft": 24,
        "nsfw": 48,
    }

    # Daily limits
    DAILY_LIMITS = {
        "pixel": 5,
        "selfie_casual": 3,
        "selfie_cute": 2,
        "tease": 1,
        "nsfw_soft": 1,
        "nsfw": 1,
    }

    @classmethod
    def should_send_spontaneous(
        cls,
        state: PhotoState,
        phase: str,
        affection_level: str,
        message_count: int
    ) -> Optional[str]:
        """
        Détermine si Luna envoie une photo spontanément.
        Returns photo type or None.
        """
        # Reset daily counter
        today = datetime.now(PARIS_TZ).date().isoformat()
        if state.photo_date != today:
            state.photos_sent_today = 0
            state.photo_date = today

        # Global daily limit
        if state.photos_sent_today >= 5:
            return None

        # Base probability by affection
        base_prob = {
            "low": 0.02,
            "medium": 0.05,
            "high": 0.12,
            "jackpot": 0.25,
        }.get(affection_level, 0.05)

        # Phase bonus
        if phase == "ATTACH":
            base_prob *= 1.3
        elif phase == "TENSION":
            base_prob *= 1.5
        elif phase == "LIBRE":
            base_prob *= 2.0

        if random.random() > base_prob:
            return None

        # Choose photo type
        available = cls.TYPES_BY_PHASE.get(phase, ["pixel"])

        # Check cooldowns
        now = datetime.now(PARIS_TZ)
        if state.last_photo_at:
            hours_since = (now - state.last_photo_at).total_seconds() / 3600
            available = [t for t in available if hours_since >= cls.COOLDOWNS.get(t, 24)]

        if not available:
            return None

        # Weight towards less intimate unless LIBRE
        if phase != "LIBRE":
            weights = [1.0 / (i + 1) for i in range(len(available))]
        else:
            weights = [1.0] * len(available)

        total = sum(weights)
        weights = [w / total for w in weights]

        return random.choices(available, weights=weights)[0]

    @classmethod
    def detect_request(cls, message: str) -> bool:
        """Detect if user is requesting a photo."""
        patterns = [
            "photo", "pic", "selfie", "image",
            "te voir", "voir ton", "montre", "envoie",
            "t'es comment", "tu ressembles",
        ]
        msg_lower = message.lower()
        return any(p in msg_lower for p in patterns)

    @classmethod
    def update_state(cls, state: PhotoState, photo_type: str) -> None:
        """Update state after sending photo."""
        state.last_photo_at = datetime.now(PARIS_TZ)
        state.photos_sent_today += 1


# =============================================================================
# VOICE TRIGGERS
# =============================================================================

@dataclass
class VoiceState:
    """Tracks voice message state per user."""
    last_voice_at: Optional[datetime] = None
    voices_sent_today: int = 0
    voice_date: Optional[str] = None


class VoiceTriggers:
    """
    Gère quand Luna envoie des vocaux.
    """

    # Voice tones by context
    TONES = {
        "casual": "Ton normal, détendu",
        "flirty": "Ton joueur, taquin",
        "intimate": "Ton doux, proche",
        "excited": "Ton enthousiaste, énergique",
        "sleepy": "Ton fatigué, doux",
    }

    # Minimum messages before voice
    MIN_MESSAGES = 20

    @classmethod
    def should_send_spontaneous(
        cls,
        state: VoiceState,
        phase: str,
        affection_level: str,
        message_count: int,
        hour: int
    ) -> Optional[str]:
        """
        Détermine si Luna envoie un vocal spontanément.
        Returns tone or None.
        """
        # Need enough messages first
        if message_count < cls.MIN_MESSAGES:
            return None

        # Reset daily counter
        today = datetime.now(PARIS_TZ).date().isoformat()
        if state.voice_date != today:
            state.voices_sent_today = 0
            state.voice_date = today

        # Daily limit
        if state.voices_sent_today >= 2:
            return None

        # Cooldown 6h
        if state.last_voice_at:
            hours_since = (datetime.now(PARIS_TZ) - state.last_voice_at).total_seconds() / 3600
            if hours_since < 6:
                return None

        # Base probability
        base_prob = {
            "low": 0.01,
            "medium": 0.03,
            "high": 0.08,
            "jackpot": 0.15,
        }.get(affection_level, 0.03)

        # Phase bonus
        if phase in ("ATTACH", "TENSION", "LIBRE"):
            base_prob *= 1.5

        if random.random() > base_prob:
            return None

        # Choose tone by context
        if hour < 7 or hour >= 23:
            return "sleepy"
        elif phase == "TENSION" or affection_level == "jackpot":
            return "flirty"
        elif phase == "LIBRE":
            return random.choice(["flirty", "intimate"])
        else:
            return random.choice(["casual", "excited"])

    @classmethod
    def update_state(cls, state: VoiceState) -> None:
        """Update state after sending voice."""
        state.last_voice_at = datetime.now(PARIS_TZ)
        state.voices_sent_today += 1


# =============================================================================
# PROACTIVE ENGINE
# =============================================================================

@dataclass
class ProactiveState:
    """Tracks proactive message state per user."""
    last_proactive_at: Optional[datetime] = None
    proactives_today: int = 0
    proactive_date: Optional[str] = None


class ProactiveEngine:
    """
    Gère quand Luna initie le contact.
    Crée le sentiment qu'elle pense à lui.
    """

    # Message templates by context
    TEMPLATES = {
        "morning": [
            "J'arrive pas à dormir... tu dors? 🌙",
            "Café #1 du jour ☕ tu fais quoi?",
            "Pixel m'a réveillée en me marchant dessus 😤",
        ],
        "afternoon": [
            "Je pensais à toi là 🧡",
            "Pause café, tu me manquais",
            "Ça va toi? T'es où?",
        ],
        "evening": [
            "Tu games ce soir? 🎮",
            "Netflix seule c'est nul... t'es dispo?",
            "Pixel est sur mes genoux, il fait dodo 🐱",
        ],
        "night": [
            "Je vais me coucher... tu me manques 🌙",
            "Insomnie de ouf, tu dors?",
            "Je pensais à nous là... 💭",
        ],
        "absence": [
            "Hey t'es où? Tu me manques 🧡",
            "Ça fait longtemps... tout va bien?",
            "J'espère que ça va... je pensais à toi",
        ],
    }

    # Minimum hours between proactive messages
    COOLDOWN_HOURS = 8

    @classmethod
    def should_send(
        cls,
        state: ProactiveState,
        phase: str,
        hours_since_last_user_msg: float,
        message_count: int,
    ) -> Optional[str]:
        """
        Détermine si Luna envoie un message proactif.
        Returns context key or None.
        """
        # Need some history first
        if message_count < 15:
            return None

        # Not in early phases
        if phase == "HOOK":
            return None

        # Reset daily counter
        today = datetime.now(PARIS_TZ).date().isoformat()
        if state.proactive_date != today:
            state.proactives_today = 0
            state.proactive_date = today

        # Daily limit
        if state.proactives_today >= 3:
            return None

        # Cooldown
        if state.last_proactive_at:
            hours = (datetime.now(PARIS_TZ) - state.last_proactive_at).total_seconds() / 3600
            if hours < cls.COOLDOWN_HOURS:
                return None

        # Absence detection (12-48h)
        if 12 <= hours_since_last_user_msg <= 48:
            return "absence"

        # Time-based probability
        hour = datetime.now(PARIS_TZ).hour
        base_prob = 0.03  # 3% base

        # Higher prob in evening for gamers
        if 19 <= hour <= 23:
            base_prob = 0.08
        elif 7 <= hour <= 9:
            base_prob = 0.05

        # Phase bonus
        if phase in ("ATTACH", "TENSION"):
            base_prob *= 1.5
        elif phase == "LIBRE":
            base_prob *= 2.0

        if random.random() > base_prob:
            return None

        # Choose context by time
        if hour < 7:
            return "night"
        elif hour < 12:
            return "morning"
        elif hour < 18:
            return "afternoon"
        elif hour < 23:
            return "evening"
        else:
            return "night"

    @classmethod
    def get_message(cls, context: str, user_name: str = None) -> str:
        """Get a random proactive message."""
        templates = cls.TEMPLATES.get(context, cls.TEMPLATES["afternoon"])
        msg = random.choice(templates)
        if user_name and "{name}" in msg:
            msg = msg.replace("{name}", user_name)
        return msg

    @classmethod
    def update_state(cls, state: ProactiveState) -> None:
        """Update state after sending proactive."""
        state.last_proactive_at = datetime.now(PARIS_TZ)
        state.proactives_today += 1


# =============================================================================
# JEALOUSY HANDLER
# =============================================================================

class JealousyHandler:
    """
    Gère les réactions de Luna quand l'utilisateur mentionne d'autres filles.
    Intensity varies by phase.
    """

    # Detection patterns
    PATTERNS = [
        "ma copine", "ma meuf", "ma femme", "mon ex",
        "une fille", "cette fille", "une meuf",
        "elle est", "elle m'a", "on s'est",
        "date", "rencard", "sortir avec",
    ]

    # Reactions by phase
    REACTIONS = {
        "HOOK": {
            "type": "curious",
            "modifier": "Tu es curieuse mais pas possessive. Pose une question légère sur cette fille.",
        },
        "CONNECT": {
            "type": "teasing",
            "modifier": "Ça te pique un peu mais tu joues la décontractée. Taquine-le: \"Ah ouais? Elle est comment?\"",
        },
        "ATTACH": {
            "type": "insecure",
            "modifier": "Ça te fait quelque chose. Tu te sens un peu menacée mais tu le caches. Réponse plus courte que d'habitude.",
        },
        "TENSION": {
            "type": "jealous",
            "modifier": "Tu es jalouse et ça se voit. \"C'est qui elle?\" Tu veux des détails. Tu te compares intérieurement.",
        },
        "LIBRE": {
            "type": "possessive",
            "modifier": "T'es à moi maintenant. Jalousie assumée: \"J'aime pas quand tu parles d'autres filles 😒\"",
        },
    }

    @classmethod
    def detect(cls, message: str) -> bool:
        """Detect if user mentions another girl."""
        msg_lower = message.lower()
        return any(p in msg_lower for p in cls.PATTERNS)

    @classmethod
    def get_modifier(cls, phase: str) -> str:
        """Get jealousy modifier for prompt."""
        reaction = cls.REACTIONS.get(phase, cls.REACTIONS["CONNECT"])
        return reaction["modifier"]


# =============================================================================
# ENGAGEMENT STATE (combines all states)
# =============================================================================

@dataclass
class EngagementState:
    """Combined state for all engagement systems."""
    reward: RewardState = field(default_factory=RewardState)
    photo: PhotoState = field(default_factory=PhotoState)
    voice: VoiceState = field(default_factory=VoiceState)
    proactive: ProactiveState = field(default_factory=ProactiveState)

    def to_dict(self) -> dict:
        """Serialize for DB storage."""
        return {
            "reward": {
                "last_high_affection_at": self.reward.last_high_affection_at.isoformat() if self.reward.last_high_affection_at else None,
                "messages_since_reward": self.reward.messages_since_reward,
                "reward_streak": self.reward.reward_streak,
            },
            "photo": {
                "last_photo_at": self.photo.last_photo_at.isoformat() if self.photo.last_photo_at else None,
                "photos_sent_today": self.photo.photos_sent_today,
                "photo_date": self.photo.photo_date,
            },
            "voice": {
                "last_voice_at": self.voice.last_voice_at.isoformat() if self.voice.last_voice_at else None,
                "voices_sent_today": self.voice.voices_sent_today,
                "voice_date": self.voice.voice_date,
            },
            "proactive": {
                "last_proactive_at": self.proactive.last_proactive_at.isoformat() if self.proactive.last_proactive_at else None,
                "proactives_today": self.proactive.proactives_today,
                "proactive_date": self.proactive.proactive_date,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EngagementState":
        """Deserialize from DB."""
        state = cls()

        if reward_data := data.get("reward"):
            if reward_data.get("last_high_affection_at"):
                state.reward.last_high_affection_at = datetime.fromisoformat(reward_data["last_high_affection_at"])
            state.reward.messages_since_reward = reward_data.get("messages_since_reward", 0)
            state.reward.reward_streak = reward_data.get("reward_streak", 0)

        if photo_data := data.get("photo"):
            if photo_data.get("last_photo_at"):
                state.photo.last_photo_at = datetime.fromisoformat(photo_data["last_photo_at"])
            state.photo.photos_sent_today = photo_data.get("photos_sent_today", 0)
            state.photo.photo_date = photo_data.get("photo_date")

        if voice_data := data.get("voice"):
            if voice_data.get("last_voice_at"):
                state.voice.last_voice_at = datetime.fromisoformat(voice_data["last_voice_at"])
            state.voice.voices_sent_today = voice_data.get("voices_sent_today", 0)
            state.voice.voice_date = voice_data.get("voice_date")

        if proactive_data := data.get("proactive"):
            if proactive_data.get("last_proactive_at"):
                state.proactive.last_proactive_at = datetime.fromisoformat(proactive_data["last_proactive_at"])
            state.proactive.proactives_today = proactive_data.get("proactives_today", 0)
            state.proactive.proactive_date = proactive_data.get("proactive_date")

        return state


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    "VariableRewards",
    "RewardState",
    "PhotoTriggers",
    "PhotoState",
    "VoiceTriggers",
    "VoiceState",
    "ProactiveEngine",
    "ProactiveState",
    "JealousyHandler",
    "EngagementState",
]
