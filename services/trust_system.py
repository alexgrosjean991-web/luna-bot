"""
Trust System - Luna V7
----------------------
Score de confiance invisible qui évolue selon les actions de l'utilisateur.

Le trust affecte:
- Niveau de vulnérabilité de Luna
- Accès aux secrets/révélations
- Réactions aux moments difficiles
- Profondeur des conversations
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TrustAction(Enum):
    """Actions qui affectent le trust score."""
    # Positives
    REMEMBERED_DETAIL = ("remembered_detail", +2)
    PRESENT_DURING_VULNERABLE = ("present_vulnerable", +3)
    REASSURED_WITHOUT_ASKING = ("reassured", +3)
    DAILY_CONSISTENCY = ("daily_consistency", +1)
    SHARED_VULNERABILITY = ("shared_vulnerability", +4)
    KEPT_PROMISE = ("kept_promise", +2)
    LISTENED_WITHOUT_JUDGING = ("listened", +2)
    DEFENDED_HER = ("defended", +5)
    GOOD_AFTERCARE = ("good_aftercare", +4)
    GOOD_REACTION_TO_SECRET = ("good_secret_reaction", +5)

    # Négatives
    IGNORED_VULNERABLE_MESSAGE = ("ignored_vulnerable", -5)
    MENTIONED_OTHER_GIRLS_BADLY = ("other_girls", -3)
    CHANGED_SUBJECT_WHEN_OPENING = ("changed_subject", -4)
    DISAPPEARED_WITHOUT_WARNING = ("disappeared", -3)
    INCONSISTENT_BEHAVIOR = ("inconsistent", -2)
    HARSH_CRITICISM = ("harsh_criticism", -4)
    FORGOT_IMPORTANT_DETAIL = ("forgot_detail", -2)
    BAD_AFTERCARE = ("bad_aftercare", -5)
    BAD_REACTION_TO_SECRET = ("bad_secret_reaction", -6)
    MINIMIZED_FEELINGS = ("minimized", -3)

    def __init__(self, action_id: str, impact: int):
        self.action_id = action_id
        self.impact = impact


@dataclass
class TrustState:
    """État actuel du trust."""
    score: int  # 0-100
    level: str  # low, medium, high, deep
    can_be_vulnerable: bool
    secret_layer_unlocked: int  # 0-5


# Trust levels
TRUST_LEVELS = {
    "low": (0, 30),
    "medium": (31, 55),
    "high": (56, 80),
    "deep": (81, 100)
}

# Default starting trust
DEFAULT_TRUST = 50


def get_trust_level(score: int) -> str:
    """Retourne le niveau de trust basé sur le score."""
    for level, (min_val, max_val) in TRUST_LEVELS.items():
        if min_val <= score <= max_val:
            return level
    return "medium"


def get_trust_state(score: int, phase: str) -> TrustState:
    """
    Calcule l'état complet du trust.

    Args:
        score: Score de trust actuel (0-100)
        phase: Phase relationnelle actuelle

    Returns:
        TrustState avec toutes les infos
    """
    level = get_trust_level(score)

    # Peut être vulnérable si trust >= medium ET phase >= interest
    can_be_vulnerable = (
        score >= 40 and
        phase in ("interest", "connection", "intimacy", "depth")
    )

    # Layer de secrets débloqué
    # Layer 0: toujours
    # Layer 1: trust >= 30 + phase >= interest
    # Layer 2: trust >= 45 + phase >= connection
    # Layer 3: trust >= 60 + phase >= connection
    # Layer 4: trust >= 75 + phase >= intimacy
    # Layer 5: trust >= 90 + phase == depth

    phase_order = ["discovery", "interest", "connection", "intimacy", "depth"]
    phase_idx = phase_order.index(phase) if phase in phase_order else 0

    layer = 0
    if score >= 30 and phase_idx >= 1:
        layer = 1
    if score >= 45 and phase_idx >= 2:
        layer = 2
    if score >= 60 and phase_idx >= 2:
        layer = 3
    if score >= 75 and phase_idx >= 3:
        layer = 4
    if score >= 90 and phase_idx >= 4:
        layer = 5

    return TrustState(
        score=score,
        level=level,
        can_be_vulnerable=can_be_vulnerable,
        secret_layer_unlocked=layer
    )


def apply_trust_action(current_score: int, action: TrustAction) -> int:
    """
    Applique une action au trust score.

    Args:
        current_score: Score actuel
        action: Action à appliquer

    Returns:
        Nouveau score (clamped 0-100)
    """
    new_score = current_score + action.impact
    new_score = max(0, min(100, new_score))

    logger.info(f"Trust: {current_score} → {new_score} ({action.action_id}: {action.impact:+d})")

    return new_score


def detect_trust_action(
    user_message: str,
    luna_last_state: str,
    memory: dict,
    hours_since_last: float
) -> TrustAction | None:
    """
    Détecte automatiquement certaines actions de trust basées sur le contexte.

    Args:
        user_message: Message de l'utilisateur
        luna_last_state: Dernier état de Luna (vulnerable, etc.)
        memory: Mémoire de l'utilisateur
        hours_since_last: Heures depuis le dernier message

    Returns:
        TrustAction détectée ou None
    """
    message_lower = user_message.lower()

    # Disparition sans prévenir (24h+)
    if hours_since_last >= 24:
        return TrustAction.DISAPPEARED_WITHOUT_WARNING

    # Présent pendant moment vulnérable
    if luna_last_state == "vulnerable" and hours_since_last < 1:
        return TrustAction.PRESENT_DURING_VULNERABLE

    # A ignoré un message vulnérable (répond après longtemps)
    if luna_last_state == "vulnerable" and hours_since_last > 6:
        return TrustAction.IGNORED_VULNERABLE_MESSAGE

    # Réassurance détectée
    reassurance_patterns = [
        "je suis là", "t'inquiète", "c'est normal", "je comprends",
        "t'es pas seule", "ça va aller", "je reste"
    ]
    if any(p in message_lower for p in reassurance_patterns):
        if luna_last_state in ("vulnerable", "anxious", "stressed"):
            return TrustAction.REASSURED_WITHOUT_ASKING

    # Partage de vulnérabilité
    vulnerability_patterns = [
        "moi aussi j'ai", "je t'avoue", "c'est dur pour moi",
        "j'ai peur", "je me sens", "ça me fait flipper"
    ]
    if any(p in message_lower for p in vulnerability_patterns):
        return TrustAction.SHARED_VULNERABILITY

    # Minimisation des sentiments
    minimization_patterns = [
        "c'est pas grave", "c'est rien", "t'exagères",
        "tu te fais des films", "calme toi"
    ]
    if any(p in message_lower for p in minimization_patterns):
        if luna_last_state in ("vulnerable", "anxious", "stressed"):
            return TrustAction.MINIMIZED_FEELINGS

    # Mention d'autres filles (à améliorer avec le contexte)
    other_girls_patterns = [
        "une autre fille", "ma pote elle", "mon ex",
        "cette meuf", "une fille"
    ]
    # Note: La jalousie est gérée séparément dans immersion.py
    # Ici on détecte les mentions potentiellement négatives

    return None


def get_trust_modifier(trust_score: int) -> str | None:
    """
    Retourne un modifier de prompt basé sur le trust level.

    Args:
        trust_score: Score de trust actuel

    Returns:
        Instruction à ajouter au prompt ou None
    """
    level = get_trust_level(trust_score)

    if level == "low":
        return """## TRUST BAS
Luna est sur ses gardes. Elle:
- Garde ses distances émotionnelles
- Teste plus, partage moins
- Humour comme bouclier
- Méfiante des intentions
"""

    if level == "deep":
        return """## TRUST PROFOND
Luna fait vraiment confiance. Elle:
- Peut être totalement vulnérable
- Partage ses peurs profondes
- Dit ce qu'elle ressent vraiment
- Se bat pour la relation
"""

    return None  # Medium/high = comportement normal


def calculate_daily_trust_bonus(
    consecutive_days: int,
    avg_response_time_hours: float
) -> int:
    """
    Calcule le bonus de trust pour la constance quotidienne.

    Args:
        consecutive_days: Jours consécutifs de conversation
        avg_response_time_hours: Temps de réponse moyen

    Returns:
        Bonus de trust (0-3)
    """
    bonus = 0

    # Bonus pour jours consécutifs
    if consecutive_days >= 3:
        bonus += 1
    if consecutive_days >= 7:
        bonus += 1
    if consecutive_days >= 14:
        bonus += 1

    # Malus si réponses très lentes en moyenne
    if avg_response_time_hours > 12:
        bonus -= 1

    return max(0, bonus)
