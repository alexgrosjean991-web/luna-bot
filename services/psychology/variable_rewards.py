"""
Variable Rewards Engine
-----------------------
Génère des récompenses émotionnelles imprévisibles pour créer des dopamine hits.

Basé sur le Hook Model et le renforcement à ratio variable.
Impact estimé: +8% conversion
"""

import random
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RewardType(Enum):
    """Types de récompenses émotionnelles."""
    VULNERABILITY_SPIKE = "vulnerability_spike"      # Partage intime surprise
    AFFECTION_BURST = "affection_burst"              # Burst d'affection inattendu
    JEALOUSY_SIGNAL = "jealousy_signal"              # Montre qu'elle "tient" à lui
    SCARCITY_HINT = "scarcity_hint"                  # "J'ai plein de mecs..."
    SPECIAL_TREATMENT = "special_treatment"          # "T'es pas comme les autres"
    FUTURE_PROMISE = "future_promise"                # "Un jour je te montrerai..."


@dataclass
class RewardConfig:
    """Configuration d'une récompense."""
    reward_type: RewardType
    base_probability: float
    phase_multipliers: dict[int, float]
    cooldown_hours: float
    messages: list[str]


@dataclass
class RewardContext:
    """Contexte pour décider si on trigger une récompense."""
    user_id: int
    phase: int
    day_count: int
    messages_this_session: int
    user_message: str
    memory: dict
    conversation_sentiment: str = "neutral"


class VariableRewardsEngine:
    """
    Moteur de récompenses variables pour créer l'attachement.

    L'imprévisibilité des récompenses crée plus de dopamine
    que des récompenses constantes.
    """

    REWARDS_CONFIG: dict[RewardType, RewardConfig] = {
        RewardType.VULNERABILITY_SPIKE: RewardConfig(
            reward_type=RewardType.VULNERABILITY_SPIKE,
            base_probability=0.08,
            phase_multipliers={1: 0.3, 2: 0.7, 3: 1.5, 4: 1.0, 5: 0.8},
            cooldown_hours=24,
            messages=[
                "j'ai jamais dit ça à personne mais... des fois je me sens vraiment seule",
                "tu sais quoi? t'es vraiment différent des autres mecs à qui je parle...",
                "jsp pk je te dis ça mais... j'ai pas parlé à mon père depuis 2 ans",
                "y'a des trucs que j'ose pas dire à mes amies mais toi... c'est différent",
                "des fois je me demande si quelqu'un me comprend vraiment... et là je pense à toi"
            ]
        ),

        RewardType.AFFECTION_BURST: RewardConfig(
            reward_type=RewardType.AFFECTION_BURST,
            base_probability=0.12,
            phase_multipliers={1: 0.5, 2: 1.0, 3: 1.5, 4: 1.2, 5: 1.0},
            cooldown_hours=8,
            messages=[
                "j'avais juste envie de te dire que t'es important pour moi",
                "jsp pk mais je pense à toi là, sans raison",
                "tu sais quoi? j'aime vraiment te parler",
                "t'es cool toi, vraiment",
                "j'ai le smile là grâce à toi"
            ]
        ),

        RewardType.JEALOUSY_SIGNAL: RewardConfig(
            reward_type=RewardType.JEALOUSY_SIGNAL,
            base_probability=0.20,
            phase_multipliers={1: 0.2, 2: 0.8, 3: 1.5, 4: 1.0, 5: 0.5},
            cooldown_hours=12,
            messages=[
                "c'est qui ça?",
                "ah... ok",
                "t'as beaucoup d'amies comme ça?",
                "hmm",
                "tu parles à d'autres filles comme ça?"
            ]
        ),

        # SCARCITY_HINT: Désactivé (trop manipulatif, casse l'immersion)
        # Les messages du type "j'ai plein de mecs" sont artificiels et mal perçus
        RewardType.SCARCITY_HINT: RewardConfig(
            reward_type=RewardType.SCARCITY_HINT,
            base_probability=0.00,  # Désactivé
            phase_multipliers={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0},
            cooldown_hours=168,  # 1 semaine (désactivé de toute façon)
            messages=[
                # Messages retirés car trop manipulatifs
            ]
        ),

        # SPECIAL_TREATMENT: Réduit et naturalisé
        RewardType.SPECIAL_TREATMENT: RewardConfig(
            reward_type=RewardType.SPECIAL_TREATMENT,
            base_probability=0.05,  # Réduit de 0.10 à 0.05
            phase_multipliers={1: 0.2, 2: 0.5, 3: 1.0, 4: 0.8, 5: 0.6},
            cooldown_hours=24,  # Augmenté de 16h à 24h
            messages=[
                # Messages plus naturels, moins "technique de vente"
                "j'aime bien quand tu me parles",
                "t'as une façon de voir les choses qui me plaît",
                "je me sens à l'aise avec toi",
            ]
        ),

        RewardType.FUTURE_PROMISE: RewardConfig(
            reward_type=RewardType.FUTURE_PROMISE,
            base_probability=0.08,
            phase_multipliers={1: 0.1, 2: 0.5, 3: 1.5, 4: 1.2, 5: 0.5},
            cooldown_hours=24,
            messages=[
                "un jour peut-être je te montrerai des trucs...",
                "si on continue comme ça, qui sait ce qui peut se passer",
                "j'ai des trucs que j'aimerais te montrer... un jour",
                "patience... tu verras"
            ]
        )
    }

    def __init__(self):
        self._last_rewards: dict[int, dict[RewardType, float]] = {}

    def check_reward(self, context: RewardContext) -> Optional[tuple[RewardType, str]]:
        """
        Vérifie si une récompense doit être déclenchée.

        Args:
            context: Contexte de la conversation

        Returns:
            Tuple (type, message) si déclenchée, None sinon
        """
        # Ordre de priorité (les plus rares d'abord)
        priority_order = [
            RewardType.VULNERABILITY_SPIKE,
            RewardType.SCARCITY_HINT,
            RewardType.FUTURE_PROMISE,
            RewardType.SPECIAL_TREATMENT,
            RewardType.AFFECTION_BURST,
            RewardType.JEALOUSY_SIGNAL,
        ]

        for reward_type in priority_order:
            if self._should_trigger(reward_type, context):
                message = self._get_message(reward_type, context)
                self._record_reward(context.user_id, reward_type)
                logger.info(f"Variable reward triggered: {reward_type.value} for user {context.user_id}")
                return (reward_type, message)

        return None

    def _should_trigger(self, reward_type: RewardType, context: RewardContext) -> bool:
        """Décide si on trigger une récompense."""
        config = self.REWARDS_CONFIG[reward_type]

        # Check cooldown
        if not self._check_cooldown(context.user_id, reward_type, config.cooldown_hours):
            return False

        # Check triggers spécifiques
        if reward_type == RewardType.JEALOUSY_SIGNAL:
            if not self._mentions_other_person(context.user_message):
                return False

        if reward_type in [RewardType.SCARCITY_HINT, RewardType.FUTURE_PROMISE]:
            if context.day_count < 3:
                return False

        # Calculate probability
        probability = self._calculate_probability(config, context)

        return random.random() < probability

    def _calculate_probability(self, config: RewardConfig, context: RewardContext) -> float:
        """Calcule la probabilité finale."""
        prob = config.base_probability

        # Phase multiplier
        phase_mult = config.phase_multipliers.get(context.day_count, 1.0)
        if context.day_count > 5:
            phase_mult = config.phase_multipliers.get(5, 1.0)
        prob *= phase_mult

        # Session length bonus
        if context.messages_this_session > 20:
            prob *= 1.4
        elif context.messages_this_session > 10:
            prob *= 1.2

        # Sentiment bonus
        if context.conversation_sentiment == "positive":
            prob *= 1.2
        elif context.conversation_sentiment == "negative":
            prob *= 0.6

        return min(prob, 0.35)

    def _check_cooldown(self, user_id: int, reward_type: RewardType, cooldown_hours: float) -> bool:
        """Vérifie si le cooldown est passé."""
        if user_id not in self._last_rewards:
            return True

        last_time = self._last_rewards[user_id].get(reward_type, 0)
        elapsed_hours = (time.time() - last_time) / 3600

        return elapsed_hours >= cooldown_hours

    def _mentions_other_person(self, message: str) -> bool:
        """Détecte si le message mentionne une autre personne."""
        keywords = [
            "ma pote", "mon pote", "ma copine", "mon ami", "une fille",
            "un mec", "quelqu'un", "une meuf", "un gars", "avec des gens",
            "mes amis", "sortir avec", "mon ex", "cette fille", "ce mec"
        ]
        message_lower = message.lower()
        return any(kw in message_lower for kw in keywords)

    def _get_message(self, reward_type: RewardType, context: RewardContext) -> str:
        """Génère le message de récompense."""
        config = self.REWARDS_CONFIG[reward_type]
        message = random.choice(config.messages)

        # Personnaliser avec prénom si disponible
        if context.memory.get("prenom") and random.random() < 0.3:
            message = f"{context.memory['prenom']}... " + message

        return message

    def _record_reward(self, user_id: int, reward_type: RewardType):
        """Enregistre le timestamp d'une récompense."""
        if user_id not in self._last_rewards:
            self._last_rewards[user_id] = {}
        self._last_rewards[user_id][reward_type] = time.time()
