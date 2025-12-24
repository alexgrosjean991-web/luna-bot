"""Proactive message handler for Luna Bot."""
import json
import logging
from datetime import datetime

from telegram.ext import ContextTypes

from settings import PARIS_TZ
from middleware.metrics import metrics

from services.db import (
    get_pool, get_users_for_proactive, count_proactive_today, log_proactive,
    get_user_data, get_emotional_state, set_emotional_state,
)
from services.relationship import get_relationship_phase
from services.subscription import (
    is_trial_expired, should_send_preparation, get_preparation_message,
    mark_preparation_sent, has_preparation_been_sent, has_paywall_been_sent,
)
from services.emotional_peaks import should_trigger_emotional_peak, get_emotional_opener
from services.proactive import (
    get_message_type_for_time, should_send, get_random_message, MAX_PROACTIVE_PER_DAY
)
from services import conversion


logger = logging.getLogger(__name__)


async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui envoie les messages proactifs par phase avec emotional peaks."""
    users = await get_users_for_proactive(inactive_hours=0)
    now = datetime.now(PARIS_TZ)
    current_hour = now.hour

    for user in users:
        try:
            user_id = user["id"]
            telegram_id = user["telegram_id"]

            # Verifier quota journalier
            count = await count_proactive_today(user_id)
            if count >= MAX_PROACTIVE_PER_DAY:
                continue

            # Recuperer phase
            user_data = await get_user_data(user_id)
            first_message_at = user_data.get("first_message_at")
            phase, day_count = get_relationship_phase(first_message_at)

            # Verifier paywall
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
            # CRITICAL FIX: utiliser etat persistant
            if not message and day_count in [3, 4, 5]:
                current_emotional_state = await get_emotional_state(user_id)
                if current_emotional_state is None:
                    if should_trigger_emotional_peak(day_count, current_hour):
                        message = get_emotional_opener(day_count)
                        msg_type = "emotional_peak"
                        await set_emotional_state(user_id, "opener")
                        logger.info(f"Emotional peak triggered for user {user_id} (day {day_count})")

            # 2b. V6: Check relance message (apres conversion non payee)
            if not message:
                relance = await conversion.get_relance_message(user_id)
                if relance:
                    message = relance
                    msg_type = "conversion_relance"
                    logger.info(f"Conversion relance sent to user {user_id}")

            # 3. Regular proactive message
            if not message:
                # Check type de message pour cette heure
                msg_type = get_message_type_for_time(phase)
                if not msg_type:
                    continue

                # Check probabilite
                if not should_send(msg_type, phase):
                    continue

                # Generer le message
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
