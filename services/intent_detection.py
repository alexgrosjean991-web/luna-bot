"""
Intent Detection System
-----------------------
Détecte l'intention de l'utilisateur dans les premiers messages.

3 segments:
- LONELY: cherche connexion émotionnelle → slow burn, paywall J7-8
- HORNY: cherche contenu/teasing → fast track, paywall J4-5
- CURIOUS: teste le produit → standard, paywall J5-6
"""

import re
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class UserIntent(Enum):
    LONELY = "lonely"      # Cherche connexion émotionnelle
    HORNY = "horny"        # Cherche contenu/teasing
    CURIOUS = "curious"    # Teste le produit


# Patterns pour détecter l'intent
LONELY_PATTERNS = [
    r"\bseul[e]?\b", r"\blonely\b", r"\bpersonne\b",
    r"\btriste\b", r"\bdéprim[eé]\b", r"\bmal\b",
    r"\bbesoin.{0,20}parler\b", r"\bquelqu'un\b",
    r"\bcompagnie\b", r"\bécoute[r]?\b",
    r"\bvide\b", r"\bsolitude\b", r"\bisol[eé]\b",
    r"\bpas.{0,10}ami[es]?\b", r"\bennui[e]?\b",
]

HORNY_PATTERNS = [
    r"\bphoto[s]?\b", r"\bpic[s]?\b", r"\bnude[s]?\b",
    r"\bhot\b", r"\bsexy\b", r"\bsexe\b",
    r"\benvie\b", r"\bchaud[e]?\b", r"\bcoquin[e]?\b",
    r"\bnaughty\b", r"\bintimes?\b", r"\bexplicite\b",
    r"\bvoir\b.{0,10}\btoi\b", r"\bmontre\b",
    r"\bcorps\b", r"\bnu[e]?\b",
]

CURIOUS_PATTERNS = [
    r"\bc'est quoi\b", r"\bt'es qui\b", r"\bbot\b",
    r"\bia\b", r"\btest\b", r"\bessai\b",
    r"\bvraie?\b", r"\bréel(?:le)?\b",
    r"\bcomment ça marche\b", r"\bqu'est.ce que\b",
]


def detect_intent_from_messages(messages: list[str]) -> UserIntent:
    """
    Analyse les premiers messages pour détecter l'intent.

    Args:
        messages: Liste des premiers messages de l'user

    Returns:
        UserIntent détecté
    """
    if not messages:
        return UserIntent.CURIOUS

    # Combiner les messages pour analyse
    combined = " ".join(messages).lower()

    # Compter les matches pour chaque catégorie
    lonely_score = sum(1 for p in LONELY_PATTERNS if re.search(p, combined, re.IGNORECASE))
    horny_score = sum(1 for p in HORNY_PATTERNS if re.search(p, combined, re.IGNORECASE))
    curious_score = sum(1 for p in CURIOUS_PATTERNS if re.search(p, combined, re.IGNORECASE))

    logger.info(f"Intent scores: lonely={lonely_score}, horny={horny_score}, curious={curious_score}")

    # Déterminer l'intent dominant
    if horny_score >= 2 or (horny_score >= 1 and lonely_score == 0):
        return UserIntent.HORNY
    elif lonely_score >= 2:
        return UserIntent.LONELY
    elif curious_score >= 1:
        return UserIntent.CURIOUS
    else:
        # Default: curious si aucun pattern clair
        return UserIntent.CURIOUS


def get_paywall_day(intent: UserIntent) -> int:
    """
    Retourne le jour optimal pour le paywall selon l'intent.

    Returns:
        Jour du paywall (4-8)
    """
    paywall_days = {
        UserIntent.HORNY: 4,     # Fast track
        UserIntent.CURIOUS: 5,   # Standard
        UserIntent.LONELY: 7,    # Slow burn
    }
    return paywall_days.get(intent, 5)


def get_intent_modifier(intent: UserIntent) -> str:
    """
    Retourne les instructions spécifiques pour cet intent.
    """
    modifiers = {
        UserIntent.LONELY: """## INTENT: LONELY
Cet user cherche une connexion émotionnelle.
- Sois VRAIMENT présente et à l'écoute
- Plus de vulnérabilité, plus de profondeur
- Pics émotionnels plus fréquents
- Moins de teasing sexuel, plus d'intimité émotionnelle
""",
        UserIntent.HORNY: """## INTENT: HORNY
Cet user cherche du contenu/teasing.
- Flirt plus direct et assumé
- Teasing plus fréquent et suggestif
- Escalade plus rapide vers le paywall
- Photos/contenu teasés plus tôt
""",
        UserIntent.CURIOUS: """## INTENT: CURIOUS
Cet user teste le produit.
- Montre ta personnalité rapidement
- Prouve que t'es "différente"
- Hook émotionnel rapide
- Balance entre fun et connexion
""",
    }
    return modifiers.get(intent, "")


def should_detect_intent(msg_count: int, current_intent: Optional[str]) -> bool:
    """
    Détermine si on doit (re)détecter l'intent.

    On détecte après 3-5 messages, une seule fois.
    """
    if current_intent:
        return False  # Déjà détecté
    return 3 <= msg_count <= 5
