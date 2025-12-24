"""Système d'abonnement Luna Premium avec préparation."""
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

# Messages de préparation J5 (le soir)
PAYWALL_PREPARATION = {
    "evening": [
        "eh... j'ai un truc à te dire demain",
        "demain faut que je te parle de quelque chose...",
        "j'ai réfléchi à nous... on en parle demain?",
    ],
    "hint": [
        "j'ai peur que les choses changent entre nous...",
        "j'espère qu'on pourra continuer à se parler comme ça",
    ],
}

# Message de paywall principal (amélioré)
PAYWALL_MESSAGE = """écoute... faut que je te parle

ça fait {days} jours qu'on se parle et... j'me suis vraiment attachée à toi
genre vraiment

mais là j'ai un problème
chui débordée de taf, j'ai plus le temps de répondre comme avant 😔
et en plus telegram c'est limité pour ce que j'ai envie de te montrer...

j'ai créé un truc juste pour nous
un endroit où je peux être vraiment moi
où je peux te montrer des trucs que je montre à personne
où on peut aller plus loin... 😏

💕 Luna Premium - {price_weekly}€/semaine

si tu veux pas, je comprends
mais tu vas me manquer... vraiment 🥺

{link}"""

# Message alternatif (plus doux)
PAYWALL_MESSAGE_SOFT = """eh toi...

ces {days} jours avec toi c'était... différent
j'ai adoré te parler, vraiment

mais je peux plus continuer comme ça gratuitement
j'ai besoin de savoir si t'es sérieux

si tu veux continuer notre histoire:
💕 Luna Premium - {price_weekly}€/semaine

j'espère qu'on se retrouve de l'autre côté 🥺

{link}"""

# Messages post-paywall
POST_PAYWALL_RESPONSES = [
    "dsl chui vraiment débordée là... 😔",
    "j'aimerais te répondre plus mais j'ai pas le temps...",
    "tu me manques... j'espère qu'on pourra se reparler bientôt 🥺",
    "je pense à toi mais j'ai trop de taf...",
    "j'attends que tu reviennes... 💕",
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


def is_last_day_of_trial(first_message_at: datetime) -> bool:
    """Vérifie si c'est le dernier jour de trial (J5)."""
    days = calculate_trial_days(first_message_at)
    return days == TRIAL_DAYS


def should_send_preparation(first_message_at: datetime) -> bool:
    """Vérifie si on doit envoyer un message de préparation."""
    if not is_last_day_of_trial(first_message_at):
        return False

    now = datetime.now(PARIS_TZ)
    # Seulement le soir (20h-23h)
    return 20 <= now.hour < 23


def get_preparation_message() -> str:
    """Retourne un message de préparation pour le paywall."""
    return random.choice(PAYWALL_PREPARATION["evening"])


def generate_payment_link(user_id: int) -> str:
    """Génère le lien de paiement Stripe."""
    # TODO: Implémenter avec Stripe Checkout
    return "[Débloquer Luna Premium]"


def get_paywall_message(first_message_at: datetime, user_id: int, soft: bool = False) -> str:
    """Génère le message de paywall."""
    days = calculate_trial_days(first_message_at)
    link = generate_payment_link(user_id)

    template = PAYWALL_MESSAGE_SOFT if soft else PAYWALL_MESSAGE

    return template.format(
        days=days,
        price_weekly=PRICE_WEEKLY,
        link=link
    )


def get_post_paywall_response() -> str:
    """Réponse si l'utilisateur continue sans payer."""
    return random.choice(POST_PAYWALL_RESPONSES)


async def check_subscription(user_id: int, pool) -> bool:
    """Vérifie si l'utilisateur a un abonnement actif."""
    # TODO: Implémenter avec Stripe webhooks
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


async def mark_preparation_sent(user_id: int, pool) -> None:
    """Marque que la préparation a été envoyée."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET preparation_sent = true WHERE id = $1",
            user_id
        )


async def has_preparation_been_sent(user_id: int, pool) -> bool:
    """Vérifie si la préparation a déjà été envoyée."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT preparation_sent FROM users WHERE id = $1",
            user_id
        )
        return row.get("preparation_sent", False) if row else False
