"""Luna Bot - GFE Complet avec mood/relationship/subscription."""
import json
import logging
import time
import signal
import sys
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN


# ============== MEDIUM FIX: Structured JSON logging ==============
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        return json.dumps(log_data, ensure_ascii=False)


# ============== MEDIUM FIX: Basic metrics tracking ==============
class Metrics:
    """Simple internal metrics tracker."""

    def __init__(self):
        self.messages_processed = 0
        self.errors_count = 0
        self.llm_calls = 0
        self.llm_errors = 0
        self.last_error: str | None = None
        self.last_error_time: float | None = None

    def record_message(self):
        self.messages_processed += 1

    def record_error(self, error: str):
        self.errors_count += 1
        self.last_error = error
        self.last_error_time = time.time()

    def record_llm_call(self, success: bool = True):
        self.llm_calls += 1
        if not success:
            self.llm_errors += 1

    def get_stats(self) -> dict:
        return {
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "llm_calls": self.llm_calls,
            "llm_errors": self.llm_errors,
            "llm_success_rate": f"{(1 - self.llm_errors / max(1, self.llm_calls)) * 100:.1f}%",
            "last_error": self.last_error,
        }


metrics = Metrics()
from services.db import (
    init_db, close_db, save_message, get_history, get_pool,
    get_or_create_user, get_user_memory, update_user_memory, increment_message_count,
    update_last_active, get_users_for_proactive, count_proactive_today, log_proactive,
    get_user_data, update_teasing_stage,
    # CRITICAL FIX: États persistants
    get_emotional_state, set_emotional_state, set_last_message_time
)
from services.llm import generate_response
from services.memory import extract_memory
from services.mood import get_current_mood, get_mood_instructions, get_mood_context
from services.availability import send_with_natural_delay
from services.relationship import get_relationship_phase, get_phase_instructions
from services.subscription import (
    is_trial_expired, get_paywall_message, get_post_paywall_response,
    mark_paywall_sent, has_paywall_been_sent,
    should_send_preparation, get_preparation_message,
    mark_preparation_sent, has_preparation_been_sent
)
from services.teasing import check_teasing_opportunity, get_teasing_instruction
from services.proactive import (
    get_message_type_for_time, should_send, get_random_message, MAX_PROACTIVE_PER_DAY
)
from services.emotional_peaks import (
    should_trigger_emotional_peak, get_emotional_opener, EMOTIONAL_STATES
)
from services.story_arcs import get_story_context

# ============== MEDIUM FIX: Configurable logging ==============
import os
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "json" or "text"

if LOG_FORMAT == "json":
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
else:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
logger = logging.getLogger(__name__)

# Extraction mémoire tous les X messages
MEMORY_EXTRACTION_INTERVAL = 5

# ============== HIGH FIX: Rate limiting robuste ==============
class RateLimiter:
    """Rate limiter avec sliding window."""

    def __init__(self, window_seconds: float = 60.0, max_requests: int = 20):
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._requests: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur peut envoyer un message."""
        now = time.time()

        # Nettoyer les anciennes requêtes
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < self.window_seconds
        ]

        # Vérifier la limite
        if len(self._requests[user_id]) >= self.max_requests:
            return False

        # Enregistrer la requête
        self._requests[user_id].append(now)
        return True

    def get_wait_time(self, user_id: int) -> float:
        """Retourne le temps d'attente avant de pouvoir renvoyer."""
        if not self._requests[user_id]:
            return 0
        oldest = min(self._requests[user_id])
        return max(0, self.window_seconds - (time.time() - oldest))


# 20 messages par minute max
rate_limiter = RateLimiter(window_seconds=60.0, max_requests=20)

# ============== CRITICAL FIX: Sanitization ==============
MAX_MESSAGE_LENGTH = 2000


def sanitize_input(text: str | None) -> str | None:
    """Valide et nettoie l'entrée utilisateur."""
    if not text:
        return None

    # Limiter la longueur
    text = text[:MAX_MESSAGE_LENGTH]

    # Supprimer caractères de contrôle (sauf newlines)
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r')

    return text.strip() or None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start."""
    user = await get_or_create_user(update.effective_user.id)
    welcome = "hey 😊 t'es qui toi?"
    await save_message(user["id"], "assistant", welcome)
    await update.message.reply_text(welcome)


# ============== HIGH FIX: Health check ==============
import os
from datetime import datetime

HEALTH_FILE = "/tmp/luna_health"
BOT_START_TIME = datetime.now()


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /health - vérifie l'état du bot."""
    try:
        # Vérifier la DB
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "✅ OK"
    except Exception as e:
        db_status = f"❌ {e}"

    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Get metrics
    stats = metrics.get_stats()

    health_msg = f"""🏥 Health Check

**Bot**: ✅ Running
**DB**: {db_status}
**Uptime**: {hours}h {minutes}m {seconds}s

📊 **Metrics**:
• Messages: {stats['messages_processed']}
• LLM calls: {stats['llm_calls']} (success: {stats['llm_success_rate']})
• Errors: {stats['errors_count']}
• Rate limiter: {len(rate_limiter._requests)} users
"""
    if stats['last_error']:
        health_msg += f"\n⚠️ Last error: {stats['last_error'][:50]}"

    await update.message.reply_text(health_msg, parse_mode="Markdown")


def write_health_file():
    """Écrit un fichier health pour Docker."""
    try:
        with open(HEALTH_FILE, "w") as f:
            f.write(str(datetime.now().timestamp()))
    except Exception:
        pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal avec tous les systèmes intégrés."""
    tg_user = update.effective_user
    telegram_id = tg_user.id

    # CRITICAL FIX: Sanitization des entrées
    user_text = sanitize_input(update.message.text)
    if not user_text:
        return

    # HIGH FIX: Rate limiting robuste (sliding window)
    if not rate_limiter.is_allowed(telegram_id):
        wait_time = rate_limiter.get_wait_time(telegram_id)
        logger.warning(f"Rate limit: {tg_user.first_name} (wait {wait_time:.0f}s)")
        return

    logger.info(f"[{tg_user.first_name}] {user_text[:100]}...")  # Tronquer dans les logs

    # Track metrics
    metrics.record_message()

    # 1. Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # 2. Update last_active + last_message_at (persistant)
    await update_last_active(user_id)
    await set_last_message_time(user_id)

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
        paywall_sent = await has_paywall_been_sent(user_id, get_pool())

        if not paywall_sent:
            # Premier message après trial: envoyer paywall
            paywall_msg = get_paywall_message(first_message_at, user_id)
            await update.message.reply_text(paywall_msg)
            await save_message(user_id, "assistant", paywall_msg)
            await mark_paywall_sent(user_id, get_pool())
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

    # 10. CRITICAL FIX: Get emotional state from DB (persistant)
    emotional_state = await get_emotional_state(user_id)

    logger.info(f"User {user_id}: Phase={phase}, Day={day_count}, Mood={mood}, EmotionalState={emotional_state}")

    # 11. Progress emotional state if user responded (persistant)
    if emotional_state == "opener":
        await set_emotional_state(user_id, "follow_up")
        emotional_state = "follow_up"
    elif emotional_state == "follow_up":
        await set_emotional_state(user_id, "resolution")
        emotional_state = "resolution"
    elif emotional_state == "resolution":
        await set_emotional_state(user_id, None)
        emotional_state = None  # Don't pass to LLM, peak is over

    # 12. Check teasing opportunity (J2-5)
    teasing_msg = None
    if 2 <= day_count <= 5:
        teasing_msg = check_teasing_opportunity(day_count, user_data)
        if teasing_msg:
            await update_teasing_stage(user_id, user_data.get("teasing_stage", 0) + 1)

    # 13. Générer réponse
    try:
        response = await generate_response(
            user_text, history, memory, phase, day_count, mood, emotional_state
        )
        metrics.record_llm_call(success=True)
    except Exception as e:
        metrics.record_llm_call(success=False)
        metrics.record_error(str(e))
        logger.error(f"LLM generation failed: {e}")
        response = "dsl j'ai bugé 😅"

    # 14. Ajouter teasing si opportun
    if teasing_msg:
        response = response + "\n\n" + teasing_msg

    # 15. Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # 16. MEDIUM FIX: Extraction mémoire périodique avec error handling
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        try:
            logger.info(f"Extraction mémoire pour user {user_id} (msg #{msg_count})")
            updated_history = await get_history(user_id, limit=10)
            new_memory = await extract_memory(updated_history, memory)
            await update_user_memory(user_id, new_memory)
        except Exception as e:
            # Ne pas bloquer la conversation si l'extraction échoue
            logger.error(f"Memory extraction failed for user {user_id}: {e}")

    # 17. Envoyer avec délai naturel
    await send_with_natural_delay(update, response, mood)


async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui envoie les messages proactifs par phase avec emotional peaks."""
    from datetime import datetime
    from settings import PARIS_TZ

    users = await get_users_for_proactive(inactive_hours=0)
    now = datetime.now(PARIS_TZ)
    current_hour = now.hour

    for user in users:
        try:
            user_id = user["id"]
            telegram_id = user["telegram_id"]

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

            message = None
            msg_type = "proactive"

            # 1. Check J5 preparation message (soir J5)
            if first_message_at and should_send_preparation(first_message_at):
                prep_sent = await has_preparation_been_sent(user_id, get_pool())
                if not prep_sent:
                    message = get_preparation_message()
                    msg_type = "preparation"
                    await mark_preparation_sent(user_id, get_pool())
                    logger.info(f"Preparation message sent to user {user_id}")

            # 2. Check emotional peak trigger (J3-5, specific hours)
            # CRITICAL FIX: utiliser état persistant
            if not message and day_count in [3, 4, 5]:
                current_emotional_state = await get_emotional_state(user_id)
                if current_emotional_state is None:
                    if should_trigger_emotional_peak(day_count, current_hour):
                        message = get_emotional_opener(day_count)
                        msg_type = "emotional_peak"
                        await set_emotional_state(user_id, "opener")
                        logger.info(f"Emotional peak triggered for user {user_id} (day {day_count})")

            # 3. Regular proactive message
            if not message:
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

            if not message:
                continue

            # Envoyer
            await context.bot.send_message(
                chat_id=telegram_id,
                text=message
            )

            # Logger
            await log_proactive(user_id, msg_type)
            logger.info(f"Proactive '{msg_type}' ({phase}) sent to user {user_id}")

        except Exception as e:
            metrics.record_error(f"proactive: {e}")
            logger.error(f"Error sending proactive to user {user['id']}: {e}")


async def post_init(application: Application) -> None:
    """Appelé après init."""
    await init_db()
    write_health_file()  # HIGH FIX: health check file


async def post_shutdown(application: Application) -> None:
    """Appelé avant shutdown."""
    logger.info("Graceful shutdown initiated...")
    await close_db()
    logger.info("Shutdown complete.")


# ============== MEDIUM FIX: Graceful shutdown handling ==============
_shutdown_triggered = False


def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_triggered
    if _shutdown_triggered:
        logger.warning("Force shutdown requested")
        sys.exit(1)
    _shutdown_triggered = True
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    # The Application handles the actual shutdown via its own signal handling
    # This just logs and prevents double-shutdown


def main() -> None:
    """Lance le bot."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

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
    app.add_handler(CommandHandler("health", health_check))  # HIGH FIX: health check
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
