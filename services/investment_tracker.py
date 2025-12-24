"""
Investment Tracker
------------------
Track les investissements de l'utilisateur pour mesurer l'engagement.

Weights:
- shared_secret: 10 pts
- shared_photo: 15 pts
- shared_music: 5 pts
- long_message (>100 chars): 3 pts
- emotional_support_given: 8 pts
- question_about_luna: 2 pts
- compliment_given: 4 pts
- time_spent: 1 pt/10min
- initiated_conversation: 5 pts
- responded_quickly (<5min): 2 pts

Usage:
- Personnaliser message paywall
- Rappeler investments dans loss aversion
- Segmenter user value (whale/regular/casual)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class InvestmentWeights:
    """Poids des différents types d'investissement."""
    shared_secret: int = 10
    shared_photo: int = 15
    shared_music: int = 5
    long_message: int = 3
    emotional_support: int = 8
    question_about_luna: int = 2
    compliment: int = 4
    time_per_10min: int = 1
    initiated_convo: int = 5
    quick_response: int = 2


@dataclass
class UserInvestments:
    """Suivi des investissements d'un utilisateur."""
    secrets_shared: int = 0
    photos_shared: int = 0
    music_shared: int = 0
    long_messages: int = 0
    emotional_support_given: int = 0
    questions_about_luna: int = 0
    compliments_given: int = 0
    total_time_minutes: float = 0.0
    conversations_initiated: int = 0
    quick_responses: int = 0

    def calculate_score(self, weights: InvestmentWeights = None) -> int:
        """Calcule le score total d'investissement."""
        w = weights or InvestmentWeights()

        score = (
            self.secrets_shared * w.shared_secret +
            self.photos_shared * w.shared_photo +
            self.music_shared * w.shared_music +
            self.long_messages * w.long_message +
            self.emotional_support_given * w.emotional_support +
            self.questions_about_luna * w.question_about_luna +
            self.compliments_given * w.compliment +
            int(self.total_time_minutes / 10) * w.time_per_10min +
            self.conversations_initiated * w.initiated_convo +
            self.quick_responses * w.quick_response
        )

        return score

    def get_segment(self) -> str:
        """
        Détermine le segment de l'utilisateur.

        Returns:
            'whale', 'regular', ou 'casual'
        """
        score = self.calculate_score()

        if score >= 100:
            return "whale"
        elif score >= 40:
            return "regular"
        else:
            return "casual"


# Patterns pour détecter les investissements dans les messages
SECRET_PATTERNS = [
    r"j'ai jamais dit", r"entre nous", r"je t'avoue",
    r"personne sait", r"secret", r"je te confie",
    r"je te dis ça qu'à toi", r"j'ose pas dire",
]

QUESTION_LUNA_PATTERNS = [
    r"et toi\s*\?", r"tu fais quoi", r"t'es où",
    r"tu penses quoi", r"tu aimes", r"c'est comment",
    r"parle.moi de toi", r"raconte.moi",
]

COMPLIMENT_PATTERNS = [
    r"t'es (trop )?(belle|mignonne|magnifique|canon)",
    r"j'aime bien", r"t'es (vraiment )?cool",
    r"tu me plais", r"t'es incroyable",
    r"t'es unique", r"j'adore",
]

EMOTIONAL_SUPPORT_PATTERNS = [
    r"je suis là", r"t'inquiète", r"ça va aller",
    r"je comprends", r"je suis désolé",
    r"c'est pas ta faute", r"t'es pas seule",
]

MUSIC_PATTERNS = [
    r"écoute ça", r"cette chanson", r"spotify",
    r"youtube.*music", r"soundcloud",
    r"j'écoute", r"ma playlist",
]


class InvestmentTracker:
    """Tracker des investissements utilisateur."""

    def __init__(self):
        self.weights = InvestmentWeights()

    def analyze_message(
        self,
        message: str,
        is_user_initiated: bool = False,
        response_time_seconds: float = None
    ) -> dict:
        """
        Analyse un message pour détecter les investissements.

        Args:
            message: Le message de l'utilisateur
            is_user_initiated: Si l'user a initié cette conversation
            response_time_seconds: Temps de réponse en secondes

        Returns:
            Dict des investissements détectés
        """
        investments = {
            "secret": False,
            "long_message": False,
            "question_about_luna": False,
            "compliment": False,
            "emotional_support": False,
            "music": False,
            "initiated": is_user_initiated,
            "quick_response": False,
        }

        msg_lower = message.lower()

        # Secret partagé
        if any(re.search(p, msg_lower) for p in SECRET_PATTERNS):
            investments["secret"] = True
            logger.info("Investment detected: secret shared")

        # Message long
        if len(message) > 100:
            investments["long_message"] = True

        # Question sur Luna
        if any(re.search(p, msg_lower) for p in QUESTION_LUNA_PATTERNS):
            investments["question_about_luna"] = True

        # Compliment
        if any(re.search(p, msg_lower) for p in COMPLIMENT_PATTERNS):
            investments["compliment"] = True
            logger.info("Investment detected: compliment")

        # Support émotionnel
        if any(re.search(p, msg_lower) for p in EMOTIONAL_SUPPORT_PATTERNS):
            investments["emotional_support"] = True
            logger.info("Investment detected: emotional support")

        # Musique partagée
        if any(re.search(p, msg_lower) for p in MUSIC_PATTERNS):
            investments["music"] = True
            logger.info("Investment detected: music shared")

        # Réponse rapide (<5 min)
        if response_time_seconds and response_time_seconds < 300:
            investments["quick_response"] = True

        return investments

    def get_loss_aversion_reminder(self, investments: UserInvestments) -> str:
        """
        Génère un rappel des investissements pour le paywall.
        Utilisé pour activer la loss aversion.
        """
        reminders = []

        if investments.secrets_shared > 0:
            reminders.append("les secrets que tu m'as confiés")

        if investments.emotional_support_given > 0:
            reminders.append("les fois où t'as été là pour moi")

        if investments.conversations_initiated > 2:
            reminders.append("toutes nos conversations")

        if investments.compliments_given > 0:
            reminders.append("les trucs gentils que tu m'as dit")

        if not reminders:
            return "tout ce qu'on a partagé ensemble"

        if len(reminders) == 1:
            return reminders[0]

        return ", ".join(reminders[:-1]) + " et " + reminders[-1]

    def get_segment_pricing(self, segment: str) -> dict:
        """
        Retourne le pricing selon le segment.

        Args:
            segment: 'whale', 'regular', ou 'casual'

        Returns:
            Dict avec price et message style
        """
        pricing = {
            "whale": {
                "weekly_price": 25,
                "message_style": "premium",
                "discount": None,
            },
            "regular": {
                "weekly_price": 25,
                "message_style": "standard",
                "discount": None,
            },
            "casual": {
                "weekly_price": 19,  # Discount pour convertir
                "message_style": "urgent",
                "discount": "24% off",
            },
        }
        return pricing.get(segment, pricing["regular"])


# Singleton
investment_tracker = InvestmentTracker()
