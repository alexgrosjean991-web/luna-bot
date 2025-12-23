"""Luna Bot - Entry Point (Modular)."""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN
from services.db import (
    init_db, close_db, save_message, get_history,
    get_or_create_user, get_user_memory, update_user_memory, increment_message_count
)
from services.llm import generate_response
from services.memory import extract_memory
from services.humanizer import send_with_delay

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Extraction mémoire tous les X messages
MEMORY_EXTRACTION_INTERVAL = 5


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start."""
    await update.message.reply_text("hey 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler messages texte avec extraction mémoire."""
    tg_user = update.effective_user
    telegram_id = tg_user.id
    user_text = update.message.text

    if not user_text:
        return

    logger.info(f"[{tg_user.first_name}] {user_text}")

    # 1. Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # 2. Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # 3. Incrémenter compteur
    msg_count = await increment_message_count(user_id)

    # 4. Récupérer historique + mémoire
    history = await get_history(user_id)
    memory = await get_user_memory(user_id)

    # 5. Générer réponse avec mémoire
    response = await generate_response(user_text, history, memory)

    # 6. Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # 7. Extraction mémoire périodique
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        logger.info(f"Extraction mémoire pour user {user_id} (msg #{msg_count})")
        updated_history = await get_history(user_id, limit=10)
        new_memory = await extract_memory(updated_history, memory)
        await update_user_memory(user_id, new_memory)

    # 8. Envoyer AVEC DÉLAI
    await send_with_delay(update, response)


async def post_init(application: Application) -> None:
    """Appelé après init."""
    await init_db()


async def post_shutdown(application: Application) -> None:
    """Appelé avant shutdown."""
    await close_db()


def main() -> None:
    """Lance le bot."""
    logger.info("Démarrage Luna Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Luna est en ligne!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
