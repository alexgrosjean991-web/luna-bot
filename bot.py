"""Luna Bot - GFE Complet avec mood/relationship/subscription.

Point d'entree principal. La logique est dans:
- handlers/ : Command et message handlers
- middleware/ : Rate limiting, metrics, sanitization
- services/ : Business logic (DB, LLM, momentum, etc.)
"""
import logging
import os
import signal
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from settings import TELEGRAM_BOT_TOKEN
from services.db import init_db, close_db
from middleware.metrics import JSONFormatter

# Import handlers
from handlers.commands import start, health_check, debug_command, reset_command, write_health_file
from handlers.message import handle_message
from handlers.proactive import send_proactive_messages, send_winback_messages, check_churn_risk


# ============== Logging configuration ==============
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


# ============== Application lifecycle ==============
async def post_init(application: Application) -> None:
    """Appele apres init."""
    await init_db()
    write_health_file()


async def post_shutdown(application: Application) -> None:
    """Appele avant shutdown."""
    logger.info("Graceful shutdown initiated...")
    await close_db()
    logger.info("Shutdown complete.")


# ============== Graceful shutdown handling ==============
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


def main() -> None:
    """Lance le bot."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

    logger.info("Demarrage Luna Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("health", health_check))
    app.add_handler(CommandHandler("debug", debug_command))   # Admin: etat interne
    app.add_handler(CommandHandler("reset", reset_command))   # Admin: reset user
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jobs proactifs - toutes les 30 minutes
    job_queue = app.job_queue
    job_queue.run_repeating(
        send_proactive_messages,
        interval=1800,
        first=60,
        name="proactive_job"
    )

    # Phase C: Win-back - toutes les 2 heures
    job_queue.run_repeating(
        send_winback_messages,
        interval=7200,
        first=300,
        name="winback_job"
    )

    # Phase C: Churn detection - toutes les heures
    job_queue.run_repeating(
        check_churn_risk,
        interval=3600,
        first=600,
        name="churn_job"
    )

    logger.info("Luna GFE en ligne!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
