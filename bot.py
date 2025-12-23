"""Luna Bot - Entry Point (Modular)."""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN
from services.db import init_db, close_db, save_message, get_history
from services.llm import generate_response

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start."""
    await update.message.reply_text("hey 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler messages texte."""
    user = update.effective_user
    user_id = user.id
    user_text = update.message.text

    if not user_text:
        return

    logger.info(f"[{user.first_name}] {user_text}")

    # Récupérer historique
    history = await get_history(user_id)

    # Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # Générer réponse
    response = await generate_response(user_text, history)

    # Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # Envoyer
    await update.message.reply_text(response)


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
