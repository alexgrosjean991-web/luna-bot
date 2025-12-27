"""Système de disponibilité de Luna - délais naturels."""
import os
import random
import asyncio
import logging
from datetime import datetime
from telegram import Update, constants
from config.settings import settings
PARIS_TZ = settings.PARIS_TZ

logger = logging.getLogger(__name__)

# Mode test désactivable via env var (LUNA_TEST_MODE=true)
TEST_MODE = os.getenv("LUNA_TEST_MODE", "false").lower() == "true"

# Délais de base en secondes selon l'heure
BASE_DELAYS = {
    "morning_early": (3, 8),    # 6-9h: répond mais lentement
    "morning_late": (2, 6),     # 9-12h: assez dispo
    "lunch": (2, 5),            # 12-14h: pause, dispo
    "afternoon": (4, 12),       # 14-18h: travaille, moins dispo
    "evening": (2, 5),          # 18-21h: dispo
    "night": (2, 6),            # 21-00h: dispo, parfois occupée
    "late_night": (5, 15),      # 00-6h: endormie/fatiguée
}

# Modificateurs selon le mood
MOOD_DELAY_MODIFIERS = {
    "happy": 0.8,      # Répond plus vite
    "chill": 1.0,
    "playful": 0.9,
    "flirty": 0.85,
    "tired": 1.4,      # Répond plus lentement
    "busy": 1.5,       # Occupée
    "emotional": 1.1,
}


def get_time_period(hour: int) -> str:
    """Retourne la période de la journée."""
    if 6 <= hour < 9:
        return "morning_early"
    elif 9 <= hour < 12:
        return "morning_late"
    elif 12 <= hour < 14:
        return "lunch"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 21:
        return "evening"
    elif 21 <= hour < 24:
        return "night"
    else:
        return "late_night"


def calculate_delay(mood: str = "chill") -> float:
    """Calcule le délai de réponse en secondes."""
    # Mode test: délai minimal
    if TEST_MODE:
        return 0.5

    now = datetime.now(PARIS_TZ)
    period = get_time_period(now.hour)

    # Délai de base
    min_delay, max_delay = BASE_DELAYS[period]
    base_delay = random.uniform(min_delay, max_delay)

    # Appliquer modificateur mood
    modifier = MOOD_DELAY_MODIFIERS.get(mood, 1.0)
    delay = base_delay * modifier

    # Ajouter un peu de variance
    delay *= random.uniform(0.9, 1.1)

    return max(1.5, min(delay, 20))  # Cap entre 1.5s et 20s


def calculate_typing_duration(text: str) -> float:
    """Calcule la durée de frappe réaliste."""
    # ~50ms par caractère + variance
    base = len(text) * 0.05
    variance = random.uniform(0.8, 1.2)
    duration = base * variance

    return max(1.0, min(duration, 8.0))


async def send_with_natural_delay(
    update: Update,
    text: str,
    mood: str = "chill",
    delay_modifier: int = 0
) -> None:
    """
    Envoie un message avec délai naturel et typing indicator.

    Args:
        update: Update Telegram
        text: Texte à envoyer
        mood: Humeur actuelle (affecte le délai)
        delay_modifier: V5 - Modificateur de délai en secondes (intermittent)
    """
    chat_id = update.effective_chat.id
    bot = update.get_bot()

    # 1. Calculer les délais
    think_delay = calculate_delay(mood)
    typing_duration = calculate_typing_duration(text)

    # V5: Appliquer le modificateur intermittent
    think_delay = max(0.5, think_delay + delay_modifier)

    logger.info(f"Délai: {think_delay:.1f}s réflexion + {typing_duration:.1f}s frappe")

    # 2. Phase "réflexion" (Luna lit et réfléchit)
    await asyncio.sleep(think_delay)

    # 3. Phase "frappe" avec typing indicator
    elapsed = 0
    while elapsed < typing_duration:
        try:
            await bot.send_chat_action(
                chat_id=chat_id,
                action=constants.ChatAction.TYPING
            )
        except Exception as e:
            logger.warning(f"Typing action failed: {e}")

        wait = min(4.0, typing_duration - elapsed)
        await asyncio.sleep(wait)
        elapsed += wait

    # 4. Envoyer le message
    await update.message.reply_text(text)
