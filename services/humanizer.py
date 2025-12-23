"""Comportements humains - délais et typing."""
import asyncio
import random
import logging
from telegram import Update, constants

logger = logging.getLogger(__name__)

# Configuration des délais
CHAR_DELAY_MS = 50          # 50ms par caractère
MIN_DELAY_S = 1.0           # Minimum 1 seconde
MAX_DELAY_S = 8.0           # Maximum 8 secondes
RANDOM_EXTRA_MIN_MS = 500   # Random additionnel min
RANDOM_EXTRA_MAX_MS = 1500  # Random additionnel max
TYPING_REFRESH_S = 4.0      # Refresh typing toutes les 4s


def calculate_delay(text: str) -> float:
    """
    Calcule le délai en secondes basé sur la longueur du texte.
    """
    # Délai basé sur les caractères
    char_delay = len(text) * (CHAR_DELAY_MS / 1000)

    # Ajouter du random
    random_extra = random.uniform(RANDOM_EXTRA_MIN_MS, RANDOM_EXTRA_MAX_MS) / 1000

    # Total avec caps
    total_delay = char_delay + random_extra
    total_delay = max(MIN_DELAY_S, min(MAX_DELAY_S, total_delay))

    logger.debug(f"Délai calculé: {total_delay:.2f}s pour {len(text)} chars")
    return total_delay


async def send_typing_action(chat_id: int, bot) -> None:
    """Envoie l'action 'typing' au chat."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    except Exception as e:
        logger.warning(f"Erreur typing action: {e}")


async def send_with_delay(update: Update, text: str) -> None:
    """
    Envoie un message avec délai humain et typing indicator.
    """
    chat_id = update.effective_chat.id
    bot = update.get_bot()

    # Calculer le délai
    delay = calculate_delay(text)
    logger.info(f"Envoi avec délai de {delay:.2f}s")

    # Envoyer typing et attendre
    elapsed = 0.0
    while elapsed < delay:
        await send_typing_action(chat_id, bot)
        wait_time = min(TYPING_REFRESH_S, delay - elapsed)
        await asyncio.sleep(wait_time)
        elapsed += wait_time

    # Envoyer le message
    await update.message.reply_text(text)
