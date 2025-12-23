"""
Luna Bot - Version Minimale
Juste: message → prompt + historique → Haiku → réponse
"""

import os
import logging
import httpx
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Charger le prompt
PROMPT_FILE = Path(__file__).parent / "prompt.txt"
SYSTEM_PROMPT = PROMPT_FILE.read_text(encoding="utf-8")

# Historique en mémoire (simple dict par user_id)
conversations = {}


async def call_haiku(system_prompt: str, messages: list) -> str:
    """Appel simple à Claude Haiku"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 100,  # Court!
        "system": system_prompt,
        "messages": messages[-20:]  # Derniers 20 messages
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Erreur Haiku: {e}")
        return "dsl j'ai bugé 😅"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal"""

    user = update.effective_user
    user_id = user.id
    user_text = update.message.text

    if not user_text:
        return

    logger.info(f"[{user.first_name}] {user_text}")

    # Récupérer ou créer l'historique
    if user_id not in conversations:
        conversations[user_id] = []

    history = conversations[user_id]

    # Ajouter le message user
    history.append({"role": "user", "content": user_text})

    # Appeler Haiku
    response = await call_haiku(SYSTEM_PROMPT, history)

    # Ajouter la réponse à l'historique
    history.append({"role": "assistant", "content": response})

    # Garder max 50 messages
    if len(history) > 50:
        conversations[user_id] = history[-50:]

    logger.info(f"[Luna] {response}")

    # Envoyer
    await update.message.reply_text(response)


def main():
    """Démarrer le bot"""

    logger.info("Démarrage Luna Bot (version minimale)...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Luna est en ligne!")
    app.run_polling()


if __name__ == "__main__":
    main()
