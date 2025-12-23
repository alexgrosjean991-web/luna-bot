"""Luna Bot - GFE Complet avec mood/relationship/subscription."""
import json
import logging
import time
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN
from services.db import (
    init_db, close_db, save_message, get_history, pool,
    get_or_create_user, get_user_memory, update_user_memory, increment_message_count,
    update_last_active, get_users_for_proactive, count_proactive_today, log_proactive,
    get_user_data, update_teasing_stage
)
from services.llm import generate_response
from services.memory import extract_memory
from services.mood import get_current_mood, get_mood_instructions, get_mood_context
from services.availability import send_with_natural_delay
from services.relationship import get_relationship_phase, get_phase_instructions
from services.subscription import (
    is_trial_expired, get_paywall_message, get_post_paywall_response,
    mark_paywall_sent, has_paywall_been_sent
)
from services.teasing import check_teasing_opportunity
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

# Rate limiting
RATE_LIMIT_SECONDS = 1.0
user_last_message: dict[int, float] = defaultdict(float)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start."""
    user = await get_or_create_user(update.effective_user.id)
    welcome = "hey 😊 t'es qui toi?"
    await save_message(user["id"], "assistant", welcome)
    await update.message.reply_text(welcome)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal avec tous les systèmes intégrés."""
    tg_user = update.effective_user
    telegram_id = tg_user.id
    user_text = update.message.text

    if not user_text:
        return

    # Rate limiting
    now = time.time()
    if now - user_last_message[telegram_id] < RATE_LIMIT_SECONDS:
        logger.warning(f"Rate limit: {tg_user.first_name}")
        return
    user_last_message[telegram_id] = now

    logger.info(f"[{tg_user.first_name}] {user_text}")

    # 1. Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # 2. Update last_active
    await update_last_active(user_id)

    # 3. Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # 4. Incrémenter compteur
    msg_count = await increment_message_count(user_id)

    # 5. Récupérer données utilisateur complètes
    user_data = await get_user_data(user_id)
    first_message_at = user_data.get("first_message_at")

    # 6. Calculer phase et jour
    phase, day_count = get_relationship_phase(first_message_at)

    # 7. Vérifier subscription (paywall après 5 jours)
    if first_message_at and is_trial_expired(first_message_at):
        paywall_sent = await has_paywall_been_sent(user_id, pool)

        if not paywall_sent:
            # Premier message après trial: envoyer paywall
            paywall_msg = get_paywall_message(first_message_at, user_id)
            await update.message.reply_text(paywall_msg)
            await save_message(user_id, "assistant", paywall_msg)
            await mark_paywall_sent(user_id, pool)
            logger.info(f"Paywall envoyé à user {user_id}")
            return
        else:
            # Paywall déjà envoyé: réponse limitée
            response = get_post_paywall_response()
            await update.message.reply_text(response)
            await save_message(user_id, "assistant", response)
            return

    # 8. Récupérer historique + mémoire
    history = await get_history(user_id)
    memory = await get_user_memory(user_id)

    # 9. Déterminer mood
    mood = get_current_mood()

    logger.info(f"User {user_id}: Phase={phase}, Day={day_count}, Mood={mood}")

    # 10. Check teasing opportunity (J4-5)
    teasing_msg = None
    if 4 <= day_count <= 5:
        teasing_msg = check_teasing_opportunity(day_count, user_data)
        if teasing_msg:
            await update_teasing_stage(user_id, user_data.get("teasing_stage", 0) + 1)

    # 11. Générer réponse
    response = await generate_response(
        user_text, history, memory, phase, day_count, mood
    )

    # 12. Ajouter teasing si opportun
    if teasing_msg:
        response = response + "\n\n" + teasing_msg

    # 13. Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # 14. Extraction mémoire périodique
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        logger.info(f"Extraction mémoire pour user {user_id} (msg #{msg_count})")
        updated_history = await get_history(user_id, limit=10)
        new_memory = await extract_memory(updated_history, memory)
        await update_user_memory(user_id, new_memory)

    # 15. Envoyer avec délai naturel
    await send_with_natural_delay(update, response, mood)


async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui envoie les messages proactifs par phase."""
    users = await get_users_for_proactive(inactive_hours=0)

    for user in users:
        try:
            user_id = user["id"]

            # Vérifier quota journalier
            count = await count_proactive_today(user_id)
            if count >= MAX_PROACTIVE_PER_DAY:
                continue

            # Récupérer phase
            user_data = await get_user_data(user_id)
            first_message_at = user_data.get("first_message_at")
            phase, day_count = get_relationship_phase(first_message_at)

            # Vérifier paywall
            if first_message_at and is_trial_expired(first_message_at):
                continue

            # Check type de message pour cette heure
            msg_type = get_message_type_for_time(phase)
            if not msg_type:
                continue

            # Check probabilité
            if not should_send(msg_type, phase):
                continue

            # Générer le message
            memory = user.get("memory", {})
            if isinstance(memory, str):
                memory = json.loads(memory)

            message = get_random_message(msg_type, memory, phase)

            # Envoyer
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=message
            )

            # Logger
            await log_proactive(user_id, msg_type)
            logger.info(f"Proactive '{msg_type}' ({phase}) sent to user {user_id}")

        except Exception as e:
            logger.error(f"Error sending proactive to user {user['id']}: {e}")


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

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jobs proactifs - toutes les 30 minutes
    job_queue = app.job_queue
    job_queue.run_repeating(
        send_proactive_messages,
        interval=1800,
        first=60,
        name="proactive_job"
    )

    logger.info("Luna GFE en ligne!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
