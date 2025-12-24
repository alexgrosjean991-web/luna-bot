"""
Dynamic Paywall System
----------------------
Timing du paywall basé sur l'intent et les signaux de readiness.

Intent timing:
- LONELY: J7-8 (slow burn, besoin de plus d'attachement)
- HORNY: J4-5 (fast track, déjà motivé)
- CURIOUS: J5-6 (standard)

Ready signals (chacun vaut 1 point):
- message_count > 80
- secrets_shared >= 2
- photos_shared = true
- emotional_support_given >= 2
- asked_about_photos = true
- expressed_attachment = true
- avg_response_time < 15 min

Score >= 5 = Ready for paywall
Score < 5 = Delay paywall
"""

import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ReadySignals:
    """Signaux de readiness pour le paywall."""
    message_count: int = 0
    secrets_shared: int = 0
    vulnerabilities_shared: int = 0
    emotional_support_given: int = 0
    user_initiated_count: int = 0
    attachment_score: float = 0.0
    avg_response_time_minutes: float = 60.0

    def calculate_score(self) -> int:
        """Calcule le score de readiness."""
        score = 0

        # Message count > 80
        if self.message_count > 80:
            score += 1

        # Secrets/vulnérabilités partagées >= 2
        if self.secrets_shared + self.vulnerabilities_shared >= 2:
            score += 1

        # Emotional support donné (via vulnérabilités)
        if self.vulnerabilities_shared >= 2:
            score += 1

        # User initie souvent
        if self.user_initiated_count >= 3:
            score += 1

        # Attachment score élevé
        if self.attachment_score >= 15:
            score += 1

        # Message count > 50 (bonus)
        if self.message_count > 50:
            score += 1

        # Réponses rapides
        if self.avg_response_time_minutes < 15:
            score += 1

        return score


def get_paywall_day_for_intent(intent: str) -> int:
    """
    Retourne le jour de paywall selon l'intent.

    Args:
        intent: 'lonely', 'horny', ou 'curious'

    Returns:
        Jour du paywall (4-8)
    """
    intent_days = {
        "lonely": 7,    # Slow burn
        "horny": 4,     # Fast track
        "curious": 5,   # Standard
    }
    return intent_days.get(intent, 5)


def should_show_paywall(
    day_count: int,
    intent: Optional[str],
    ready_signals: ReadySignals,
    paywall_already_sent: bool
) -> tuple[bool, str]:
    """
    Détermine si on doit montrer le paywall.

    Args:
        day_count: Jour actuel
        intent: Intent de l'user (lonely/horny/curious)
        ready_signals: Signaux de readiness
        paywall_already_sent: Si déjà envoyé

    Returns:
        (should_show, reason)
    """
    if paywall_already_sent:
        return (False, "already_sent")

    # Calculer le jour cible selon l'intent
    target_day = get_paywall_day_for_intent(intent or "curious")
    ready_score = ready_signals.calculate_score()

    logger.info(
        f"Paywall check: day={day_count}, target={target_day}, "
        f"intent={intent}, ready_score={ready_score}"
    )

    # Si score >= 5 et jour >= target - 1, on peut montrer
    if ready_score >= 5 and day_count >= target_day - 1:
        return (True, f"ready_early (score={ready_score})")

    # Si jour == target, on montre
    if day_count == target_day:
        return (True, f"target_day (score={ready_score})")

    # Si jour > target + 2, forcer le paywall
    if day_count > target_day + 2:
        return (True, f"overdue (day={day_count})")

    # Si score très faible et jour == target, delay
    if ready_score < 3 and day_count == target_day:
        return (False, f"delay_low_engagement (score={ready_score})")

    return (False, f"not_ready (day={day_count}, target={target_day})")


def get_preparation_day(intent: Optional[str]) -> int:
    """Retourne le jour de préparation (veille du paywall)."""
    paywall_day = get_paywall_day_for_intent(intent or "curious")
    return paywall_day - 1


def should_send_preparation(
    day_count: int,
    current_hour: int,
    intent: Optional[str],
    preparation_sent: bool
) -> bool:
    """
    Détermine si on doit envoyer le message de préparation.

    La préparation est envoyée le soir de la veille du paywall.
    """
    if preparation_sent:
        return False

    prep_day = get_preparation_day(intent)

    if day_count != prep_day:
        return False

    # Seulement le soir (20h-23h)
    return 20 <= current_hour < 23


def get_paywall_urgency(day_count: int, intent: Optional[str]) -> str:
    """
    Retourne le niveau d'urgence du paywall.

    Returns:
        'soft', 'standard', ou 'urgent'
    """
    target_day = get_paywall_day_for_intent(intent or "curious")

    if day_count < target_day:
        return "soft"
    elif day_count == target_day:
        return "standard"
    else:
        return "urgent"


def build_ready_signals_from_user_data(user_data: dict) -> ReadySignals:
    """
    Construit les signaux de readiness depuis les données user.

    Args:
        user_data: Dict avec les données de l'utilisateur

    Returns:
        ReadySignals
    """
    return ReadySignals(
        message_count=user_data.get("total_messages", 0),
        secrets_shared=0,  # TODO: track séparément
        vulnerabilities_shared=user_data.get("vulnerabilities_shared", 0),
        emotional_support_given=user_data.get("vulnerabilities_shared", 0),
        user_initiated_count=user_data.get("user_initiated_count", 0),
        attachment_score=user_data.get("attachment_score", 0.0),
        avg_response_time_minutes=60.0,  # TODO: calculer
    )
