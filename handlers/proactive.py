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
    get_users_for_winback, get_winback_state, update_winback_state,
    get_users_at_churn_risk, update_churn_state, get_timing_profile,
    safe_json_loads,
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
from services.winback import winback_engine, WinbackStage
from services.churn_prediction import churn_predictor, ChurnRisk
from services.user_timing import user_timing


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

            # Recuperer phase (V7: basé sur msg_count)
            user_data = await get_user_data(user_id)
            first_message_at = user_data.get("first_message_at")
            msg_count = user_data.get("total_messages", 0)  # Correct column name
            phase, _ = get_relationship_phase(msg_count)

            # Calculer day_count pour compatibilité
            if first_message_at:
                if first_message_at.tzinfo is None:
                    first_message_at = first_message_at.replace(tzinfo=PARIS_TZ)
                day_count = (now - first_message_at).days + 1
            else:
                day_count = 1

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
                    memory = safe_json_loads(memory, {}, "proactive memory")

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
            logger.exception(f"Error sending proactive to user {user['id']}")


async def send_winback_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui envoie les messages win-back aux utilisateurs churned."""
    users = await get_users_for_winback()
    now = datetime.now(PARIS_TZ)
    current_hour = now.hour

    # Ne pas envoyer la nuit
    if current_hour < 10 or current_hour > 22:
        return

    for user in users:
        try:
            user_id = user["id"]
            telegram_id = user["telegram_id"]
            last_active = user.get("last_active")

            if not last_active:
                continue

            # Calculer jours d'inactivite
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=PARIS_TZ)
            days_inactive = (now - last_active).days

            # Recuperer etat winback
            winback_state = await get_winback_state(user_id)
            last_stage = winback_state.get("winback_stage")
            last_winback_at = winback_state.get("last_winback_at")

            # Determiner si on doit envoyer
            stage = winback_engine.should_send_winback(
                days_inactive=days_inactive,
                last_winback_stage=last_stage,
                last_winback_at=last_winback_at
            )

            if not stage:
                continue

            # Verifier le timing optimal
            timing_profile = await get_timing_profile(user_id)
            peak_hours = timing_profile.get("peak_hours", [])

            if peak_hours and current_hour not in peak_hours:
                # Pas l'heure optimale, mais si urgence haute on envoie quand meme
                if stage not in (WinbackStage.STAGE_3, WinbackStage.STAGE_4):
                    continue

            # Generer le message
            memory = user.get("memory", {})
            if isinstance(memory, str):
                memory = safe_json_loads(memory, {}, "winback memory")

            message = winback_engine.get_winback_message(stage, memory)

            # Envoyer
            await context.bot.send_message(
                chat_id=telegram_id,
                text=message
            )

            # Mettre a jour l'etat
            await update_winback_state(user_id, stage.value)
            await log_proactive(user_id, f"winback_{stage.value}")

            logger.info(f"Win-back {stage.value} sent to user {user_id} (inactive {days_inactive}d)")

        except Exception as e:
            metrics.record_error(f"winback: {e}")
            logger.exception(f"Error sending winback to user {user['id']}")


async def check_churn_risk(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job qui detecte et agit sur les utilisateurs a risque de churn."""
    users = await get_users_at_churn_risk()
    now = datetime.now(PARIS_TZ)
    current_hour = now.hour

    for user in users:
        try:
            user_id = user["id"]
            telegram_id = user["telegram_id"]
            last_active = user.get("last_active")

            if not last_active:
                continue

            # Calculer heures depuis dernier message
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=PARIS_TZ)
            hours_inactive = (now - last_active).total_seconds() / 3600

            # Construire les signaux depuis les données utilisateur
            from services.churn_prediction import ChurnSignals
            total_msgs = user.get("total_messages", 0)
            session_count = user.get("session_count", 1) or 1
            user_initiated = user.get("user_initiated_count", 0) or 0
            attachment = user.get("attachment_score", 0) or 0

            signals = ChurnSignals(
                hours_since_last_message=hours_inactive,
                avg_message_length_recent=50 if total_msgs < 10 else 40,  # Estimation conservatrice
                avg_message_length_historical=50,
                messages_last_24h=0 if hours_inactive > 24 else max(1, total_msgs // 10),
                messages_last_7d=total_msgs,
                session_count_last_7d=min(session_count, 7),
                questions_asked_last_10=2 if attachment > 10 else 1,  # Basé sur attachment
                user_initiated_ratio=min(1.0, user_initiated / session_count),
                response_time_trend="stable"
            )

            # Predire le churn
            prediction = churn_predictor.predict(signals)

            # Mettre a jour l'etat
            await update_churn_state(user_id, prediction.risk.value, prediction.score)

            # Si risque moyen/haut et bon timing, envoyer message preventif
            if prediction.risk in (ChurnRisk.MEDIUM, ChurnRisk.HIGH):
                # Verifier timing
                timing_profile = await get_timing_profile(user_id)
                peak_hours = timing_profile.get("peak_hours", [20, 21])

                if current_hour in peak_hours or prediction.risk == ChurnRisk.HIGH:
                    memory = user.get("memory", {})
                    if isinstance(memory, str):
                        memory = safe_json_loads(memory, {}, "churn memory")

                    # Message personnalise selon le risque
                    if prediction.risk == ChurnRisk.HIGH:
                        prenom = memory.get("prenom", "")
                        message = f"hey{' ' + prenom if prenom else ''}... je pensais a toi, ca va?"
                    else:
                        message = "coucou, t'es passe ou? 🙈"

                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=message
                    )

                    await log_proactive(user_id, f"churn_prevention_{prediction.risk.value}")
                    logger.info(f"Churn prevention sent to user {user_id} (risk={prediction.risk.value})")

        except Exception as e:
            metrics.record_error(f"churn_check: {e}")
            logger.exception(f"Error checking churn for user {user['id']}")
