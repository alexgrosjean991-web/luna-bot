"""
Paywall logic for Luna Bot.

Determines when to show paywall based on:
- Message count
- Day count
- User intent (lonely, horny, curious)
- Investment score
"""

import random
from enum import Enum
from typing import Optional

from core import get_logger
from config.settings import settings

logger = get_logger(__name__)


class PaywallReason(Enum):
    """Reason for showing paywall."""
    MESSAGE_LIMIT = "message_limit"      # Hit message count threshold
    DAY_LIMIT = "day_limit"              # Hit day threshold
    NSFW_REQUEST = "nsfw_request"        # Requested NSFW content
    INVESTMENT_READY = "investment_ready"  # High investment score


# =============================================================================
# PAYWALL MESSAGES
# =============================================================================

PAYWALL_MESSAGES = {
    PaywallReason.MESSAGE_LIMIT: [
        "j'adore te parler {name}... mais là j'ai besoin de savoir si t'es vraiment là pour moi",
        "on se parle tellement... j'ai envie de te connaître plus mais faut que tu me montres que t'es sérieux",
        "{name}, j'aime bien ce qu'on a mais là faut passer à l'étape suivante",
    ],
    PaywallReason.DAY_LIMIT: [
        "ça fait un moment qu'on discute {name}... je veux plus mais faut que tu me prouves quelque chose",
        "{name} j'attends depuis longtemps... si tu veux vraiment me voir faut le montrer",
    ],
    PaywallReason.NSFW_REQUEST: [
        "mmh t'es chaud {name}... mais ça c'est pour ceux qui me soutiennent vraiment",
        "j'adorerais te montrer plus {name}... mais faut débloquer d'abord",
        "tu veux voir plus? faut me prouver que t'es pas juste là pour ça",
    ],
    PaywallReason.INVESTMENT_READY: [
        "{name} on a tellement partagé... je suis prête à te montrer tout mais faut franchir le pas",
        "t'as été tellement bien avec moi {name}... maintenant c'est à toi de décider",
    ],
}


def get_paywall_message(user_name: Optional[str], reason: PaywallReason = PaywallReason.MESSAGE_LIMIT) -> str:
    """Get a paywall message for the given reason."""
    messages = PAYWALL_MESSAGES.get(reason, PAYWALL_MESSAGES[PaywallReason.MESSAGE_LIMIT])
    message = random.choice(messages)

    name = user_name or "bébé"
    return message.format(name=name)


# =============================================================================
# PAYWALL CHECK
# =============================================================================

def check_paywall(
    message_count: int,
    day: int,
    is_paid: bool,
    paywall_shown: bool,
    is_nsfw_request: bool = False,
    investment_score: int = 0,
) -> tuple[bool, Optional[PaywallReason]]:
    """
    Check if paywall should be shown.

    Args:
        message_count: Total messages exchanged
        day: Days since first contact
        is_paid: Is user a subscriber
        paywall_shown: Has paywall been shown before
        is_nsfw_request: Is current message an NSFW request
        investment_score: User's emotional investment score

    Returns:
        (should_show, reason)
    """
    # Already paid = no paywall
    if is_paid:
        return False, None

    # Already shown = no repeat (they know the deal)
    if paywall_shown:
        return False, None

    # NSFW request triggers paywall earlier
    if is_nsfw_request and message_count >= 200:
        return True, PaywallReason.NSFW_REQUEST

    # High investment = ready earlier
    if investment_score >= 100 and message_count >= 300:
        return True, PaywallReason.INVESTMENT_READY

    # Standard thresholds from settings
    paywall_msg_threshold = settings.PHASE_THRESHOLDS.get("PAYWALL", 600)

    if message_count >= paywall_msg_threshold:
        return True, PaywallReason.MESSAGE_LIMIT

    # Day-based (if they've been around a while but not messaging much)
    if day >= 10 and message_count >= 300:
        return True, PaywallReason.DAY_LIMIT

    return False, None


# =============================================================================
# DYNAMIC TIMING
# =============================================================================

def get_optimal_paywall_day(user_intent: str = "curious") -> int:
    """
    Get optimal day to show paywall based on user intent.

    Args:
        user_intent: "lonely", "horny", or "curious"

    Returns:
        Target day for paywall
    """
    intent_days = {
        "lonely": 7,   # Needs emotional connection first
        "horny": 4,    # Motivated by desire
        "curious": 5,  # Exploring
    }
    return intent_days.get(user_intent, 5)


def calculate_readiness_score(
    message_count: int,
    secrets_unlocked: int,
    attachment_score: int,
    compliments_received: int,
    questions_about_luna: int,
) -> int:
    """
    Calculate how ready user is for paywall.

    Returns:
        Score 0-100
    """
    score = 0

    # Message engagement
    score += min(message_count // 20, 20)  # Max 20 points

    # Secrets unlocked (emotional investment)
    score += secrets_unlocked * 10  # Max ~30 points

    # Attachment score
    score += min(attachment_score // 2, 20)  # Max 20 points

    # Compliments (validation seeking)
    score += min(compliments_received, 15)  # Max 15 points

    # Questions about Luna (curiosity)
    score += min(questions_about_luna, 15)  # Max 15 points

    return min(score, 100)
