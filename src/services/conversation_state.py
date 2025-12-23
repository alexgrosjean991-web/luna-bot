"""
Conversation State Machine
Gère les transitions entre états de conversation.
"""

import logging
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """États de la conversation"""
    GREETING = "greeting"      # Première rencontre
    FLIRT = "flirt"            # Connexion établie, flirt léger
    TEASE = "tease"            # Tension sexuelle, sous-entendus
    NSFW_SOFT = "nsfw_soft"    # Sexting léger
    NSFW_HARD = "nsfw_hard"    # Sexting explicite
    AFTERCARE = "aftercare"    # Post-intime, câlins


@dataclass
class StateTransition:
    """Représente une transition d'état"""
    from_state: ConversationState
    to_state: ConversationState
    reason: str


class StateMachine:
    """
    Machine à états pour la conversation.
    Détermine l'état actuel basé sur l'affection, le contexte, et le message.
    """

    # Seuils d'affection pour chaque état
    AFFECTION_THRESHOLDS = {
        ConversationState.GREETING: 0,
        ConversationState.FLIRT: 20,
        ConversationState.TEASE: 35,
        ConversationState.NSFW_SOFT: 50,
        ConversationState.NSFW_HARD: 70,
        ConversationState.AFTERCARE: 50,  # Spécial - après NSFW
    }

    # Keywords pour détecter l'intention du message
    NSFW_KEYWORDS = [
        # Explicite
        "nude", "naked", "sex", "fuck", "dick", "cock", "pussy", "cum",
        "nue", "nu", "sexe", "baise", "bite", "chatte", "sucer", "jouir",
        "déshabille", "string", "culotte", "mouillée", "bandant",
        # Sensuel
        "embrasse", "caresse", "touche", "peau", "corps", "lèvres",
        "kiss", "touch", "skin", "body", "lips",
        # Suggestif
        "lit", "bed", "couette", "blottir", "cuddle", "serrer",
    ]

    AFTERCARE_KEYWORDS = [
        "c'était bon", "c'était bien", "wow", "incroyable",
        "that was", "amazing", "incredible",
        "fatigué", "tired", "dormir", "sleep",
        "câlin", "cuddle", "blottir", "bras",
    ]

    ROMANTIC_KEYWORDS = [
        "je t'aime", "love you", "tu me manques", "miss you",
        "t'es belle", "beautiful", "gorgeous", "magnifique",
        "mon coeur", "bébé", "baby", "honey",
    ]

    def __init__(self):
        self._last_states: dict = {}  # user_id -> last state

    def detect_message_intent(self, message: str) -> Tuple[bool, bool, bool]:
        """
        Détecte l'intention du message.
        Returns: (is_nsfw, is_aftercare, is_romantic)
        """
        msg_lower = message.lower()

        is_nsfw = any(kw in msg_lower for kw in self.NSFW_KEYWORDS)
        is_aftercare = any(kw in msg_lower for kw in self.AFTERCARE_KEYWORDS)
        is_romantic = any(kw in msg_lower for kw in self.ROMANTIC_KEYWORDS)

        return is_nsfw, is_aftercare, is_romantic

    def get_state(
        self,
        user_id: int,
        affection: float,
        is_converted: bool,
        user_message: str,
        last_luna_message: str = ""
    ) -> Tuple[ConversationState, Optional[StateTransition]]:
        """
        Détermine l'état actuel de la conversation.

        Args:
            user_id: ID de l'utilisateur
            affection: Niveau d'affection (0-100)
            is_converted: Si l'user a payé
            user_message: Message de l'utilisateur
            last_luna_message: Dernier message de Luna

        Returns:
            (current_state, transition if state changed)
        """
        previous_state = self._last_states.get(user_id)
        is_nsfw, is_aftercare, is_romantic = self.detect_message_intent(user_message)

        # === LOGIQUE DE DÉTERMINATION DE L'ÉTAT ===

        # 1. AFTERCARE: Après NSFW, si message aftercare détecté
        if previous_state in [ConversationState.NSFW_SOFT, ConversationState.NSFW_HARD]:
            if is_aftercare and not is_nsfw:
                new_state = ConversationState.AFTERCARE
                return self._transition(user_id, previous_state, new_state, "aftercare detected")

        # 2. NSFW_HARD: Affection >= 70, converted, message NSFW
        if affection >= 70 and is_converted and is_nsfw:
            new_state = ConversationState.NSFW_HARD
            if previous_state != new_state:
                return self._transition(user_id, previous_state, new_state, "explicit nsfw")
            return new_state, None

        # 3. NSFW_SOFT: Affection >= 50, message NSFW
        if affection >= 50 and is_nsfw:
            new_state = ConversationState.NSFW_SOFT
            if previous_state != new_state:
                return self._transition(user_id, previous_state, new_state, "soft nsfw")
            return new_state, None

        # 4. Si on était en NSFW et le message est encore NSFW, rester
        if previous_state in [ConversationState.NSFW_SOFT, ConversationState.NSFW_HARD]:
            # Check si le message continue le sexting
            if is_nsfw or self._is_sexting_continuation(user_message):
                return previous_state, None

        # 5. TEASE: Affection >= 35, message suggestif ou romantique
        if affection >= 35 and (is_romantic or is_nsfw):
            new_state = ConversationState.TEASE
            if previous_state != new_state:
                return self._transition(user_id, previous_state, new_state, "teasing mode")
            return new_state, None

        # 6. FLIRT: Affection >= 20
        if affection >= 20:
            new_state = ConversationState.FLIRT
            if previous_state != new_state:
                return self._transition(user_id, previous_state, new_state, "affection threshold")
            return new_state, None

        # 7. GREETING: Par défaut
        new_state = ConversationState.GREETING
        if previous_state and previous_state != new_state:
            return self._transition(user_id, previous_state, new_state, "reset to greeting")
        return new_state, None

    def _is_sexting_continuation(self, message: str) -> bool:
        """Détecte si le message continue un sexting en cours"""
        continuation_patterns = [
            "mmh", "oui", "encore", "continue", "plus",
            "yes", "more", "keep", "don't stop",
            "j'aime", "c'est bon", "like that",
            "...",
        ]
        msg_lower = message.lower().strip()
        return any(p in msg_lower for p in continuation_patterns) or len(msg_lower) < 30

    def _transition(
        self,
        user_id: int,
        from_state: Optional[ConversationState],
        to_state: ConversationState,
        reason: str
    ) -> Tuple[ConversationState, StateTransition]:
        """Enregistre et retourne une transition d'état"""
        self._last_states[user_id] = to_state

        transition = StateTransition(
            from_state=from_state or ConversationState.GREETING,
            to_state=to_state,
            reason=reason
        )

        logger.info(f"State transition: {from_state} -> {to_state} ({reason})")
        return to_state, transition

    def force_state(self, user_id: int, state: ConversationState) -> None:
        """Force un état (pour debug ou reset)"""
        self._last_states[user_id] = state

    def get_last_state(self, user_id: int) -> Optional[ConversationState]:
        """Retourne le dernier état connu"""
        return self._last_states.get(user_id)


# Instance globale
state_machine = StateMachine()
