"""Luna Bot - Entry Point (Modular)."""
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN
from services.db import (
    init_db, close_db, save_message, get_history,
    get_or_create_user, get_user_memory, update_user_memory, increment_message_count,
    update_last_active, get_users_for_proactive, count_proactive_today, log_proactive,
    get_user_phase
)
from services.llm import generate_response
from services.memory import extract_memory
from services.humanizer import send_with_delay
from services.proactive import (
    get_message_type_for_time, should_send, get_random_message, MAX_PROACTIVE_PER_DAY
)

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

    # 2. Update last_active
    await update_last_active(user_id)

    # 3. Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # 3. Incrémenter compteur
    msg_count = await increment_message_count(user_id)

    # 4. Récupérer historique + mémoire + phase
    history = await get_history(user_id)
    memory = await get_user_memory(user_id)
    phase, day_count = await get_user_phase(user_id)

    logger.info(f"User {user_id}: Phase={phase}, Day={day_count}")

    # 5. Générer réponse avec mémoire et phase
    response = await generate_response(user_text, history, memory, phase, day_count)

    # 6. Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # 7. Extraction mémoire périodique
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        logger.info(f"Extraction mémoire pour user {user_id} (msg #{msg_count})")
        updated_history = await get_history(user_id, limit=10)
        new_memory = await extract_memory(updated_history, memory)
        await update_user_memory(user_id, new_memory)

    # 9. Envoyer AVEC DÉLAI
    await send_with_delay(update, response)


async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui envoie les messages proactifs."""
    message_type = get_message_type_for_time()

    if not message_type:
        return

    logger.info(f"Checking proactive messages: {message_type}")

    # Récupérer les users éligibles
    if message_type == "miss_you":
        users = await get_users_for_proactive(inactive_hours=24)
    else:
        users = await get_users_for_proactive(inactive_hours=0)

    for user in users:
        try:
            # Vérifier quota journalier
            count = await count_proactive_today(user["id"])
            if count >= MAX_PROACTIVE_PER_DAY:
                continue

            # Check probabilité
            if not should_send(message_type):
                continue

            # Générer le message
            memory = user.get("memory", {})
            if isinstance(memory, str):
                memory = json.loads(memory)

            message = get_random_message(message_type, memory)

            # Envoyer
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=message
            )

            # Logger
            await log_proactive(user["id"], message_type)
            logger.info(f"Proactive '{message_type}' sent to user {user['id']}")

        except Exception as e:
            logger.error(f"Error sending proactive to user {user['id']}: {e}")


async def post_init(application: Application) -> None:
    """Appelé après init."""
    await init_db()


async def post_shutdown(application: Application) -> None:
    """Appelé avant shutdown."""
    await close_db()


def main() -> None:
    """Lance le bot avec messages proactifs."""
    logger.info("Démarrage Luna Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jobs proactifs - toutes les 30 minutes
    job_queue = app.job_queue
    job_queue.run_repeating(
        send_proactive_messages,
        interval=1800,  # 30 minutes
        first=60,       # Démarre après 1 minute
        name="proactive_job"
    )

    logger.info("Luna est en ligne avec messages proactifs!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
