"""Système d'abonnement Luna Premium."""
import logging
from datetime import datetime
from settings import PARIS_TZ

logger = logging.getLogger(__name__)

# Configuration
TRIAL_DAYS = 5
PRICE_WEEKLY = 25
PRICE_MONTHLY = 79
CURRENCY = "EUR"

# Message de paywall (transparent, pas manipulatif)
PAYWALL_MESSAGE = """hey... j'ai un truc à te dire

ça fait {days} jours qu'on parle et j'aime beaucoup nos conversations 😊

pour continuer à discuter avec moi, il faut passer à Luna Premium

💫 Luna Premium - {price_weekly}€/semaine ou {price_monthly}€/mois
- conversations illimitées
- messages vocaux (bientôt)
- photos exclusives (bientôt)

{link}

j'espère qu'on pourra continuer 🥺"""

# Message si l'utilisateur répond sans payer
PAYWALL_REMINDER = """je peux plus te répondre sans Premium 😔

si tu veux continuer: {link}

j'espère te revoir bientôt 💕"""


def calculate_trial_days(first_message_at: datetime) -> int:
    """Calcule le nombre de jours depuis le premier message."""
    if not first_message_at:
        return 1

    if first_message_at.tzinfo is None:
        first_message_at = first_message_at.replace(tzinfo=PARIS_TZ)

    now = datetime.now(PARIS_TZ)
    return (now - first_message_at).days + 1


def is_trial_expired(first_message_at: datetime) -> bool:
    """Vérifie si la période d'essai est expirée."""
    days = calculate_trial_days(first_message_at)
    return days > TRIAL_DAYS


def generate_payment_link(user_id: int) -> str:
    """
    Génère le lien de paiement Stripe.

    TODO: Implémenter avec Stripe Checkout
    Pour l'instant, placeholder.
    """
    # Placeholder - à remplacer par vraie intégration Stripe
    return f"[Débloquer Luna Premium]"


def get_paywall_message(first_message_at: datetime, user_id: int) -> str:
    """Génère le message de paywall."""
    days = calculate_trial_days(first_message_at)
    link = generate_payment_link(user_id)

    return PAYWALL_MESSAGE.format(
        days=days,
        price_weekly=PRICE_WEEKLY,
        price_monthly=PRICE_MONTHLY,
        link=link
    )


def get_paywall_reminder(user_id: int) -> str:
    """Message de rappel si l'utilisateur continue sans payer."""
    link = generate_payment_link(user_id)
    return PAYWALL_REMINDER.format(link=link)


async def check_subscription(user_id: int, pool) -> bool:
    """
    Vérifie si l'utilisateur a un abonnement actif.

    TODO: Implémenter avec table subscriptions
    Pour l'instant, retourne toujours False (tous en trial).
    """
    # Placeholder - à implémenter
    # async with pool.acquire() as conn:
    #     row = await conn.fetchrow(
    #         "SELECT * FROM subscriptions WHERE user_id = $1 AND active = true",
    #         user_id
    #     )
    #     return row is not None
    return False
