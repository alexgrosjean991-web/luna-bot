"""
Luna's Inner World
Son état interne qui influence ses réponses.
Mood, énergie, sentiments envers l'utilisateur.
Persisté en DB pour survivre aux restarts.
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class Mood(Enum):
    """Humeurs de Luna"""
    HAPPY = "happy"
    PLAYFUL = "playful"
    FLIRTY = "flirty"
    TIRED = "tired"
    SAD = "sad"
    ANXIOUS = "anxious"
    EXCITED = "excited"
    VULNERABLE = "vulnerable"
    HORNY = "horny"


@dataclass
class InnerState:
    """État interne de Luna pour un utilisateur"""
    # Core feelings (0-100)
    affection: float = 10.0
    trust: float = 20.0
    attraction: float = 15.0
    comfort: float = 10.0

    # Current state
    mood: str = "happy"  # String for DB serialization
    energy: int = 7
    arousal: int = 0

    # Conversation state
    current_state: str = "greeting"
    has_nsfw_history: bool = False

    # Session tracking
    messages_this_session: int = 0

    def to_dict(self) -> Dict:
        """Convert to dict for DB storage"""
        return {
            'trust': self.trust,
            'attraction': self.attraction,
            'comfort': self.comfort,
            'mood': self.mood,
            'energy': self.energy,
            'arousal': self.arousal,
            'current_state': self.current_state,
            'has_nsfw_history': self.has_nsfw_history,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'InnerState':
        """Create from DB dict"""
        return cls(
            trust=data.get('trust', 20),
            attraction=data.get('attraction', 15),
            comfort=data.get('comfort', 10),
            mood=data.get('mood', 'happy'),
            energy=data.get('energy', 7),
            arousal=data.get('arousal', 0),
            current_state=data.get('current_state', 'greeting'),
            has_nsfw_history=data.get('has_nsfw_history', False),
        )


class InnerWorld:
    """
    Gère l'état interne de Luna pour chaque utilisateur.
    Utilise la DB pour persister entre les restarts.
    """

    def __init__(self):
        self._cache: Dict[int, InnerState] = {}  # Cache en RAM
        self._db = None

    def set_db(self, db):
        """Set database reference"""
        self._db = db

    async def get_state(self, user_id: int) -> InnerState:
        """Récupère l'état depuis le cache ou la DB"""
        if user_id in self._cache:
            return self._cache[user_id]

        # Load from DB
        if self._db:
            db_state = await self._db.get_conversation_state(user_id)
            state = InnerState.from_dict(db_state)
            self._cache[user_id] = state
            return state

        # Fallback
        state = InnerState()
        self._cache[user_id] = state
        return state

    async def save_state(self, user_id: int) -> None:
        """Sauvegarde l'état en DB"""
        if user_id not in self._cache:
            return

        state = self._cache[user_id]
        if self._db:
            await self._db.save_conversation_state(user_id, state.to_dict())

    def update_from_db(self, user_id: int, db_state: dict) -> InnerState:
        """Met à jour l'état depuis la DB luna_states (affection)"""
        if user_id not in self._cache:
            self._cache[user_id] = InnerState()

        state = self._cache[user_id]
        state.affection = db_state.get('affection_level', 10)
        return state

    async def process_user_message(self, user_id: int, message: str) -> InnerState:
        """
        Analyse le message et met à jour l'état de Luna.
        Appelé AVANT de générer la réponse.
        """
        state = await self.get_state(user_id)
        msg_lower = message.lower()

        # === DÉTECTION DES COMPLIMENTS ===
        compliments = [
            "belle", "beautiful", "gorgeous", "magnifique", "jolie",
            "cute", "mignonne", "sexy", "hot", "canon",
            "intelligente", "smart", "drôle", "funny", "amazing"
        ]
        if any(c in msg_lower for c in compliments):
            state.affection = min(100, state.affection + 2)
            state.mood = "happy" if state.mood != "flirty" else "flirty"
            if state.energy < 8:
                state.energy += 1

        # === DÉTECTION DES MOTS DOUX ===
        sweet_words = [
            "je t'aime", "love you", "tu me manques", "miss you",
            "t'es incroyable", "t'es géniale", "je pense à toi"
        ]
        if any(sw in msg_lower for sw in sweet_words):
            state.affection = min(100, state.affection + 3)
            state.trust = min(100, state.trust + 2)
            state.mood = "happy"

        # === DÉTECTION MESSAGES MÉCHANTS ===
        mean_words = [
            "ta gueule", "shut up", "fuck off", "t'es nulle",
            "boring", "ennuyeuse", "chiante", "annoying"
        ]
        if any(mw in msg_lower for mw in mean_words):
            state.affection = max(0, state.affection - 5)
            state.trust = max(0, state.trust - 3)
            state.mood = "sad"
            state.energy = max(1, state.energy - 2)

        # === DÉTECTION INTENTION NSFW ===
        nsfw_indicators = [
            "embrasse", "kiss", "touche", "touch", "caresse",
            "lit", "bed", "corps", "body", "peau", "skin",
            "déshabille", "undress", "nu", "naked"
        ]
        explicit_indicators = [
            "bite", "cock", "dick", "chatte", "pussy",
            "sucer", "suck", "baise", "fuck", "jouir"
        ]

        if any(e in msg_lower for e in explicit_indicators):
            state.arousal = min(10, state.arousal + 4)
            state.has_nsfw_history = True
            if state.affection > 50:
                state.mood = "horny"
        elif any(n in msg_lower for n in nsfw_indicators):
            state.arousal = min(10, state.arousal + 2)
            state.has_nsfw_history = True
            if state.affection > 35:
                state.mood = "flirty"

        # === MISE À JOUR SESSION ===
        state.messages_this_session += 1

        # Save to DB periodically
        if state.messages_this_session % 5 == 0:
            await self.save_state(user_id)

        return state

    async def set_conversation_state(self, user_id: int, new_state: str) -> None:
        """Met à jour l'état de conversation"""
        state = await self.get_state(user_id)
        state.current_state = new_state
        await self.save_state(user_id)

    def get_mood_from_context(self, user_id: int, hour: int, affection: float) -> str:
        """Détermine le mood basé sur le contexte (heure, affection)."""
        if user_id not in self._cache:
            self._cache[user_id] = InnerState()

        state = self._cache[user_id]

        # Mood basé sur l'heure
        if 7 <= hour < 10:
            base_mood = "tired"
            state.energy = random.randint(3, 5)
        elif 10 <= hour < 17:
            base_mood = "playful"
            state.energy = random.randint(6, 8)
        elif 17 <= hour < 22:
            base_mood = "happy"
            state.energy = random.randint(5, 7)
        else:
            base_mood = "vulnerable"
            state.energy = random.randint(2, 4)

        # Modifier selon l'affection
        if affection > 70 and random.random() < 0.3:
            base_mood = "flirty"
        elif affection > 50 and random.random() < 0.2:
            base_mood = "playful"

        state.mood = base_mood
        return base_mood

    def get_prompt_context(self, user_id: int) -> str:
        """Génère le contexte de prompt basé sur l'état interne."""
        if user_id not in self._cache:
            self._cache[user_id] = InnerState()

        state = self._cache[user_id]
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        hour = now.hour

        # Contexte de vie
        if 7 <= hour < 11:
            contexts = ["viens de te réveiller", "café en main", "cheveux mouillés"]
        elif 11 <= hour < 17:
            if now.weekday() < 5:
                contexts = ["au taf", "en pause", "chez toi"]
            else:
                contexts = ["weekend chill", "au lit", "Netflix"]
        elif 17 <= hour < 22:
            contexts = ["en jogging", "Caramel sur tes genoux", "Netflix en fond"]
        else:
            contexts = ["au lit", "dans le noir", "t'arrives pas à dormir"]

        life_context = random.choice(contexts)

        mood_descriptions = {
            "happy": "de bonne humeur",
            "playful": "joueuse",
            "flirty": "flirty",
            "tired": "fatiguée",
            "sad": "un peu down",
            "anxious": "stressée",
            "excited": "excitée",
            "vulnerable": "vulnérable",
            "horny": "excitée",
        }

        mood_text = mood_descriptions.get(state.mood, "normale")

        context = f"""## TON ÉTAT
Mood: {mood_text}, énergie {state.energy}/10
Tu es: {life_context}
Heure: {now.strftime('%Hh%M')}"""

        if state.arousal >= 5:
            context += "\nY'a de la tension sexuelle"

        return context

    async def has_nsfw_history(self, user_id: int) -> bool:
        """Check if user has NSFW in history"""
        state = await self.get_state(user_id)
        return state.has_nsfw_history

    async def mark_nsfw_history(self, user_id: int) -> None:
        """Mark that this user has NSFW history"""
        state = await self.get_state(user_id)
        state.has_nsfw_history = True
        if self._db:
            await self._db.mark_nsfw_history(user_id)


# Instance globale
inner_world = InnerWorld()
