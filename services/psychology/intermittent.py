"""
Intermittent Reinforcement Engine
---------------------------------
Gère la variabilité dans la disponibilité et l'affection de Luna.

Principe: L'imprévisibilité crée un attachement plus fort.
Impact estimé: +4% conversion
"""

import random
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AvailabilityState(Enum):
    """États de disponibilité de Luna."""
    AVAILABLE = "available"           # Répond normalement
    SLOW = "slow"                     # Répond lentement
    EAGER = "eager"                   # Répond très vite (excitée)


class AffectionLevel(Enum):
    """Niveaux d'affection variables."""
    COLD = "cold"                     # Distante, réponses courtes
    NORMAL = "normal"                 # Comportement standard
    WARM = "warm"                     # Plus affectueuse que d'habitude
    EXTRA_SWEET = "extra_sweet"       # Très affectueuse
    NEEDY = "needy"                   # Demande attention


@dataclass
class IntermittentState:
    """État courant du système intermittent pour un user."""
    availability: AvailabilityState
    affection: AffectionLevel
    determined_at: datetime


class IntermittentEngine:
    """
    Moteur de renforcement intermittent.

    Gère:
    - Niveaux d'affection fluctuants
    - Délais de réponse variables
    - Modifications de ton
    """

    # Poids pour les états
    AVAILABILITY_WEIGHTS = {
        AvailabilityState.AVAILABLE: 0.65,
        AvailabilityState.SLOW: 0.25,
        AvailabilityState.EAGER: 0.10
    }

    AFFECTION_WEIGHTS = {
        AffectionLevel.COLD: 0.05,
        AffectionLevel.NORMAL: 0.55,
        AffectionLevel.WARM: 0.25,
        AffectionLevel.EXTRA_SWEET: 0.10,
        AffectionLevel.NEEDY: 0.05
    }

    # Délais selon disponibilité (en secondes, additionnels au délai de base)
    DELAY_MODIFIERS = {
        AvailabilityState.AVAILABLE: (0, 0),      # Pas de modification
        AvailabilityState.SLOW: (60, 180),        # +1-3min
        AvailabilityState.EAGER: (-2, -1),        # Réduit le délai
    }

    # Messages needy
    NEEDY_ADDITIONS = [
        "\n\nt'étais où??",
        "\n\ntu m'avais manqué...",
        "\n\nreste avec moi un peu",
        "\n\ntu pars pas hein?",
    ]

    # Messages extra sweet
    SWEET_ADDITIONS = [
        " t'es vraiment le meilleur",
        " j'aime trop te parler",
        " t'es adorable",
        " je suis contente de te parler",
    ]

    def __init__(self):
        self._user_states: dict[int, IntermittentState] = {}

    def get_state(self, user_id: int, day_count: int, hours_since_last: float) -> IntermittentState:
        """
        Détermine l'état actuel pour un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            day_count: Jour de la relation
            hours_since_last: Heures depuis dernier message

        Returns:
            État intermittent
        """
        # Vérifier si on a un état récent (valide 30min)
        if user_id in self._user_states:
            state = self._user_states[user_id]
            if (datetime.now() - state.determined_at).seconds < 1800:
                return state

        # Calculer nouvel état
        availability = self._determine_availability(day_count)
        affection = self._determine_affection(day_count, hours_since_last)

        state = IntermittentState(
            availability=availability,
            affection=affection,
            determined_at=datetime.now()
        )
        self._user_states[user_id] = state

        logger.debug(f"User {user_id}: availability={availability.value}, affection={affection.value}")

        return state

    def get_delay_modifier(self, state: IntermittentState) -> int:
        """
        Retourne le modificateur de délai en secondes.

        Args:
            state: État intermittent

        Returns:
            Secondes à ajouter au délai de base
        """
        min_mod, max_mod = self.DELAY_MODIFIERS[state.availability]
        return random.randint(min_mod, max_mod)

    def modify_response(self, response: str, state: IntermittentState) -> str:
        """
        Modifie une réponse selon le niveau d'affection.

        Args:
            response: Réponse originale
            state: État intermittent

        Returns:
            Réponse modifiée
        """
        if state.affection == AffectionLevel.COLD:
            return self._make_cold(response)
        elif state.affection == AffectionLevel.EXTRA_SWEET:
            return self._make_sweet(response)
        elif state.affection == AffectionLevel.NEEDY:
            return self._make_needy(response)

        return response

    def get_affection_instruction(self, state: IntermittentState) -> Optional[str]:
        """
        Retourne une instruction pour le LLM selon l'affection.

        Args:
            state: État intermittent

        Returns:
            Instruction pour le system prompt ou None
        """
        instructions = {
            AffectionLevel.COLD: (
                "Tu es un peu distante et froide dans cette réponse. "
                "Réponds de manière courte, moins d'emojis, ton neutre."
            ),
            AffectionLevel.WARM: (
                "Tu es particulièrement chaleureuse et affectueuse. "
                "Montre que tu apprécies vraiment cette conversation."
            ),
            AffectionLevel.EXTRA_SWEET: (
                "Tu es TRÈS affectueuse, presque amoureuse. "
                "Complimente-le, dis-lui qu'il te manquait, sois douce."
            ),
            AffectionLevel.NEEDY: (
                "Tu es un peu clingy/en demande d'attention. "
                "Pose des questions, demande s'il va rester, montre que tu veux son attention."
            ),
        }

        return instructions.get(state.affection)

    def _determine_availability(self, day_count: int) -> AvailabilityState:
        """Détermine la disponibilité avec pondération."""
        weights = self.AVAILABILITY_WEIGHTS.copy()

        # Phases avancées: plus de chance d'être eager
        if day_count >= 3:
            weights[AvailabilityState.EAGER] *= 1.5

        return self._weighted_choice(weights)

    def _determine_affection(self, day_count: int, hours_since_last: float) -> AffectionLevel:
        """Détermine le niveau d'affection."""
        weights = self.AFFECTION_WEIGHTS.copy()

        # Phases avancées: plus d'affection
        if day_count >= 3:
            weights[AffectionLevel.WARM] *= 1.5
            weights[AffectionLevel.EXTRA_SWEET] *= 1.5
            weights[AffectionLevel.NEEDY] *= 2

        # Longue absence: plus needy
        if hours_since_last > 12:
            weights[AffectionLevel.NEEDY] *= 2.5
        elif hours_since_last > 6:
            weights[AffectionLevel.NEEDY] *= 1.5

        # Phase 1: moins de variance
        if day_count == 1:
            weights[AffectionLevel.COLD] *= 0.3
            weights[AffectionLevel.NEEDY] *= 0.2

        return self._weighted_choice(weights)

    def _make_cold(self, response: str) -> str:
        """Rend une réponse plus froide."""
        import re

        # Enlever emojis affectueux
        response = re.sub(r'[💕🥺😊❤️💗💖]', '', response)

        # Raccourcir si trop long
        if len(response) > 80:
            sentences = response.split('. ')
            if len(sentences) > 1:
                response = sentences[0]

        return response.strip()

    def _make_sweet(self, response: str) -> str:
        """Rend une réponse plus affectueuse."""
        if random.random() < 0.6:
            response += random.choice(self.SWEET_ADDITIONS)
        return response

    def _make_needy(self, response: str) -> str:
        """Ajoute un élément needy."""
        if random.random() < 0.5:
            response += random.choice(self.NEEDY_ADDITIONS)
        return response

    def _weighted_choice(self, weights: dict) -> any:
        """Fait un choix pondéré."""
        options = list(weights.keys())
        probs = list(weights.values())
        total = sum(probs)
        probs = [p / total for p in probs]
        return random.choices(options, probs)[0]
