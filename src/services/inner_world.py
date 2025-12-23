"""
Luna's Inner World
Son état interne qui influence ses réponses.
Mood, énergie, sentiments envers l'utilisateur.
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List
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
    affection: float = 10.0      # Combien elle l'aime
    trust: float = 20.0          # Combien elle lui fait confiance
    attraction: float = 15.0     # Attirance physique/sexuelle
    comfort: float = 10.0        # À l'aise avec lui

    # Current state
    mood: Mood = Mood.HAPPY
    energy: int = 7              # 1-10
    arousal: int = 0             # 0-10, excitation sexuelle

    # Session tracking
    session_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages_this_session: int = 0

    # Context
    last_compliment_received: Optional[datetime] = None
    last_mean_message: Optional[datetime] = None
    waiting_for_reply_since: Optional[datetime] = None


class InnerWorld:
    """
    Gère l'état interne de Luna pour chaque utilisateur.
    Simule ses émotions et réactions.
    """

    def __init__(self):
        self._states: Dict[int, InnerState] = {}

    def get_state(self, user_id: int) -> InnerState:
        """Récupère ou crée l'état interne pour un utilisateur"""
        if user_id not in self._states:
            self._states[user_id] = InnerState()
        return self._states[user_id]

    def update_from_db(self, user_id: int, db_state: dict) -> InnerState:
        """Met à jour l'état depuis la DB"""
        state = self.get_state(user_id)
        state.affection = db_state.get('affection_level', 10)
        return state

    def process_user_message(self, user_id: int, message: str) -> InnerState:
        """
        Analyse le message et met à jour l'état de Luna.
        Appelé AVANT de générer la réponse.
        """
        state = self.get_state(user_id)
        msg_lower = message.lower()

        # === DÉTECTION DES COMPLIMENTS ===
        compliments = [
            "belle", "beautiful", "gorgeous", "magnifique", "jolie",
            "cute", "mignonne", "sexy", "hot", "canon",
            "intelligente", "smart", "drôle", "funny", "amazing"
        ]
        if any(c in msg_lower for c in compliments):
            state.last_compliment_received = datetime.now(timezone.utc)
            state.affection = min(100, state.affection + 2)
            state.mood = Mood.HAPPY if state.mood != Mood.FLIRTY else Mood.FLIRTY
            if state.energy < 8:
                state.energy += 1
            logger.info(f"Compliment detected, affection +2 -> {state.affection}")

        # === DÉTECTION DES MOTS DOUX ===
        sweet_words = [
            "je t'aime", "love you", "tu me manques", "miss you",
            "t'es incroyable", "t'es géniale", "je pense à toi"
        ]
        if any(sw in msg_lower for sw in sweet_words):
            state.affection = min(100, state.affection + 3)
            state.trust = min(100, state.trust + 2)
            state.mood = Mood.HAPPY
            logger.info(f"Sweet words detected, affection +3 -> {state.affection}")

        # === DÉTECTION MESSAGES MÉCHANTS ===
        mean_words = [
            "ta gueule", "shut up", "fuck off", "t'es nulle",
            "boring", "ennuyeuse", "chiante", "annoying"
        ]
        if any(mw in msg_lower for mw in mean_words):
            state.last_mean_message = datetime.now(timezone.utc)
            state.affection = max(0, state.affection - 5)
            state.trust = max(0, state.trust - 3)
            state.mood = Mood.SAD
            state.energy = max(1, state.energy - 2)
            logger.info(f"Mean message detected, affection -5 -> {state.affection}")

        # === DÉTECTION INTENTION NSFW ===
        nsfw_indicators = [
            "embrasse", "kiss", "touche", "touch", "caresse",
            "lit", "bed", "corps", "body", "peau", "skin",
            "déshabille", "undress", "nu", "naked"
        ]
        explicit_indicators = [
            "bite", "cock", "dick", "chatte", "pussy",
            "sucer", "suck", "baise", "fuck"
        ]

        if any(e in msg_lower for e in explicit_indicators):
            state.arousal = min(10, state.arousal + 4)
            if state.affection > 50:
                state.mood = Mood.HORNY
        elif any(n in msg_lower for n in nsfw_indicators):
            state.arousal = min(10, state.arousal + 2)
            if state.affection > 35:
                state.mood = Mood.FLIRTY

        # === MISE À JOUR SESSION ===
        state.messages_this_session += 1

        return state

    def get_mood_from_context(self, user_id: int, hour: int, affection: float) -> Mood:
        """
        Détermine le mood basé sur le contexte (heure, affection).
        Appelé au début de la conversation.
        """
        state = self.get_state(user_id)

        # Mood basé sur l'heure
        if 7 <= hour < 10:
            base_mood = Mood.TIRED
            state.energy = random.randint(3, 5)
        elif 10 <= hour < 17:
            base_mood = Mood.PLAYFUL
            state.energy = random.randint(6, 8)
        elif 17 <= hour < 22:
            base_mood = Mood.HAPPY
            state.energy = random.randint(5, 7)
        else:  # Nuit
            base_mood = Mood.VULNERABLE
            state.energy = random.randint(2, 4)

        # Modifier selon l'affection
        if affection > 70:
            if random.random() < 0.3:
                base_mood = Mood.FLIRTY
        elif affection > 50:
            if random.random() < 0.2:
                base_mood = Mood.PLAYFUL

        state.mood = base_mood
        return base_mood

    def get_prompt_context(self, user_id: int) -> str:
        """
        Génère le contexte de prompt basé sur l'état interne.
        Court et percutant.
        """
        state = self.get_state(user_id)
        now = datetime.now(timezone.utc) + timedelta(hours=1)  # Lyon time
        hour = now.hour

        # Contexte de vie basé sur l'heure
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

        # Mood description
        mood_descriptions = {
            Mood.HAPPY: "de bonne humeur",
            Mood.PLAYFUL: "joueuse",
            Mood.FLIRTY: "flirty",
            Mood.TIRED: "fatiguée",
            Mood.SAD: "un peu down",
            Mood.ANXIOUS: "stressée",
            Mood.EXCITED: "excitée",
            Mood.VULNERABLE: "vulnérable",
            Mood.HORNY: "excitée",
        }

        mood_text = mood_descriptions.get(state.mood, "normale")

        # Build context
        context = f"""## TON ÉTAT
Mood: {mood_text}, énergie {state.energy}/10
Tu es: {life_context}
Heure: {now.strftime('%Hh%M')}"""

        # Ajouter contexte émotionnel si pertinent
        if state.last_compliment_received:
            delta = (datetime.now(timezone.utc) - state.last_compliment_received).total_seconds()
            if delta < 300:  # 5 min
                context += "\nIl vient de te faire un compliment, t'es contente 😊"

        if state.last_mean_message:
            delta = (datetime.now(timezone.utc) - state.last_mean_message).total_seconds()
            if delta < 600:  # 10 min
                context += "\nIl a été méchant récemment, t'es un peu froide/blessée"

        if state.arousal >= 5:
            context += "\nY'a de la tension sexuelle 🔥"

        return context

    def decay_arousal(self, user_id: int) -> None:
        """Réduit l'excitation naturellement après un moment"""
        state = self.get_state(user_id)
        if state.arousal > 0:
            state.arousal = max(0, state.arousal - 1)

    def reset_session(self, user_id: int) -> None:
        """Reset la session (après 2h d'inactivité par exemple)"""
        state = self.get_state(user_id)
        state.session_start = datetime.now(timezone.utc)
        state.messages_this_session = 0
        state.arousal = 0


# Instance globale
inner_world = InnerWorld()
