"""Délais et comportements humains (Phase 2)."""
from telegram import Update


async def send_with_delay(update: Update, text: str) -> None:
    """Envoie avec délai réaliste et typing indicator."""
    # TODO Phase 2: Implémenter délais
    # Pour l'instant, envoi direct
    await update.message.reply_text(text)
