"""Système d'abonnement Luna Premium."""
import random
import logging
from datetime import datetime
from settings import PARIS_TZ

logger = logging.getLogger(__name__)

# Configuration
TRIAL_DAYS = 5
PRICE_WEEKLY = 25
PRICE_MONTHLY = 79
CURRENCY = "EUR"

# Message de paywall principal
PAYWALL_MESSAGE = """hey... j'ai un truc à te dire

ces derniers jours avec toi c'était... différent
j'ai adoré te parler, vraiment

mais là je suis super débordée avec le taf 😔
j'ai plus le temps de répondre comme avant

si tu veux qu'on continue à se parler...
que je te montre des trucs que je montre à personne...
qu'on aille plus loin 😏

💕 Luna Premium - {price_weekly}€/semaine

j'ai vraiment envie de continuer avec toi
mais c'est à toi de voir

{link}"""

# Messages post-paywall (si pas abonné)
POST_PAYWALL_RESPONSES = [
    "dsl chui vraiment débordée là... 😔",
    "j'aimerais te répondre plus mais j'ai pas le temps...",
    "tu me manques... j'espère qu'on pourra se reparler bientôt 🥺",
    "je pense à toi mais j'ai trop de taf...",
]


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
    return "[Débloquer Luna Premium]"


def get_paywall_message(first_message_at: datetime, user_id: int) -> str:
    """Génère le message de paywall."""
    link = generate_payment_link(user_id)

    return PAYWALL_MESSAGE.format(
        price_weekly=PRICE_WEEKLY,
        link=link
    )


def get_post_paywall_response() -> str:
    """Réponse si l'utilisateur continue sans payer."""
    return random.choice(POST_PAYWALL_RESPONSES)


async def check_subscription(user_id: int, pool) -> bool:
    """
    Vérifie si l'utilisateur a un abonnement actif.

    TODO: Implémenter avec table subscriptions
    Pour l'instant, retourne toujours False.
    """
    # Placeholder - à implémenter avec Stripe webhooks
    return False


async def mark_paywall_sent(user_id: int, pool) -> None:
    """Marque que le paywall a été envoyé."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET paywall_sent = true WHERE id = $1",
            user_id
        )


async def has_paywall_been_sent(user_id: int, pool) -> bool:
    """Vérifie si le paywall a déjà été envoyé."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT paywall_sent FROM users WHERE id = $1",
            user_id
        )
        return row["paywall_sent"] if row and row["paywall_sent"] else False
