"""Luna Bot - GFE Complet avec mood/relationship/subscription."""
import json
import logging
import time
import signal
import sys
import random
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from settings import TELEGRAM_BOT_TOKEN, BOT_VERSION, ADMIN_TELEGRAM_ID


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
    get_emotional_state, set_emotional_state, set_last_message_time,
    # V5: Psychology data
    get_inside_jokes, update_inside_jokes, get_pending_events, update_pending_events,
    update_attachment_score, increment_session_count, increment_vulnerabilities,
    get_psychology_data, get_last_message_time,
    # V8: Luna mood system
    get_mood_state, update_luna_mood
)

# V5: Psychology modules
from services.psychology.variable_rewards import VariableRewardsEngine, RewardContext
from services.psychology.inside_jokes import InsideJokesEngine, InsideJoke
from services.psychology.intermittent import IntermittentEngine
from services.psychology.memory_callbacks import MemoryCallbacksEngine, PendingEvent
from services.psychology.attachment import AttachmentTracker
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

# V7: Transition system (legacy, kept for compatibility)
from services.levels import (
    ConversationLevel, EmotionalState, TransitionManager,
    detect_level, detect_climax
)
from services.db import (
    get_transition_state, update_transition_state, start_cooldown,
    # V3: Momentum system
    get_momentum_state, update_momentum_state, start_climax_recovery,
    reset_momentum, reset_intimacy_history
)

# V3: Momentum-based routing
from services.momentum import momentum_engine, Intensity
from services.llm_router import get_llm_config_v3, get_llm_config, is_premium_session
from services.prompt_selector import get_prompt_for_tier, get_tier_name, get_prompt_for_tier_v7

# V8: Luna mood system
from services.luna_mood import luna_mood_engine, LunaMood
from prompts.deflect import get_deflect_prompt, get_luna_initiates_prompt
from services.llm import call_with_graceful_fallback
from services import conversion
from settings import PAYMENT_LINK
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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

# V5: Psychology engines
variable_rewards = VariableRewardsEngine()
inside_jokes = InsideJokesEngine()
intermittent = IntermittentEngine()
memory_callbacks = MemoryCallbacksEngine()
attachment_tracker = AttachmentTracker()

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


def detect_engagement_signal(text: str) -> int:
    """Détecte les signaux d'engagement positif pour le teasing stage.

    Returns: 0 (neutre), 1 (engagement léger), 2 (engagement fort)
    """
    text_lower = text.lower()

    # Signaux forts (+2): flirt explicite, compliments, enthousiasme
    strong_signals = [
        'j\'adore', 'trop belle', 'magnifique', 'canon', 'sublime',
        't\'es incroyable', 'tu me plais', 'j\'ai envie', 'tu me manques',
        'je kiffe', 'trop mignonne', 'j\'aime trop', 'tu me rends fou',
        '😍', '🥰', '😘', '❤️', '💕', '🔥'
    ]
    for signal in strong_signals:
        if signal in text_lower:
            return 2

    # Signaux légers (+1): intérêt, questions personnelles, positivité
    light_signals = [
        'tu fais quoi', 'raconte', 'et toi', 'parle moi', 'dis moi',
        'c\'est cool', 'j\'aime bien', 'intéressant', 'haha', 'mdr',
        '😊', '😏', '🙈', '💋'
    ]
    for signal in light_signals:
        if signal in text_lower:
            return 1

    return 0


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

**Bot**: ✅ Running (v{BOT_VERSION})
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


# ============== ADMIN: Debug & Reset ==============

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /debug - affiche l'état interne d'un user (admin only)."""
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return

    # Parse target user (self or specified)
    args = context.args
    if args and args[0].isdigit():
        target_telegram_id = int(args[0])
    else:
        target_telegram_id = update.effective_user.id

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", target_telegram_id
            )

        if not user:
            await update.message.reply_text(f"❌ User {target_telegram_id} non trouvé")
            return

        # Calculate day_count
        first_msg = user.get("first_message_at")
        if first_msg:
            from settings import PARIS_TZ
            now = datetime.now(PARIS_TZ)
            day_count = (now.date() - first_msg.date()).days + 1
        else:
            day_count = 1

        # Format memory
        memory = user.get("memory", {})
        if isinstance(memory, str):
            import json
            memory = json.loads(memory) if memory else {}

        memory_str = ", ".join(f"{k}: {v}" for k, v in memory.items() if v) or "vide"

        # V3: Momentum data
        momentum = user.get('momentum', 0) or 0
        tier = user.get('current_tier', 1) or 1
        intimacy = user.get('intimacy_history', 0) or 0
        msgs_since_climax = user.get('messages_since_climax', 999) or 999

        tier_names = {1: "SFW (Haiku)", 2: "FLIRT (Magnum)", 3: "NSFW (Magnum)"}
        tier_str = tier_names.get(tier, f"Tier {tier}")

        # V7: NSFW state
        nsfw_state = momentum_engine.get_nsfw_state(momentum, msgs_since_climax)
        nsfw_state_str = nsfw_state.upper() if tier >= 3 else "N/A"

        # V8: Luna mood data
        luna_mood = user.get('luna_mood', 'normal') or 'normal'
        mood_updated = user.get('mood_updated_at')
        last_horny = user.get('last_horny_at')

        debug_msg = f"""🔍 **Debug User {target_telegram_id}**

📊 **État Général**
• Messages: {user.get('total_messages', 0)}
• Jour: J{day_count}
• Phase: {user.get('phase', 'discovery')}
• Subscription: {user.get('subscription_status', 'trial')}

🔥 **Momentum (V7)**
• Momentum: {momentum:.1f}/100
• Tier actuel: {tier_str}
• État NSFW: {nsfw_state_str}
• Intimacy history: {intimacy} sessions NSFW
• Msgs depuis climax: {msgs_since_climax}
• Msgs cette session: {user.get('messages_this_session', 0)}

😊 **Luna Mood (V8)**
• Mood actuel: {luna_mood.upper()}
• Dernière MAJ: {mood_updated or 'jamais'}
• Dernier horny: {last_horny or 'jamais'}

💕 **Engagement**
• Teasing stage: {user.get('teasing_stage', 0)}/8
• Emotional state: {user.get('emotional_state') or 'None'}
• Attachment score: {user.get('attachment_score', 0):.1f}/100
• Premium previews: {user.get('premium_preview_count', 0)}

🧠 **Mémoire**
{memory_str[:200]}

⏰ **Timestamps**
• First msg: {user.get('first_message_at')}
• Last active: {user.get('last_active')}
• Paywall sent: {user.get('paywall_sent', False)}
"""
        await update.message.reply_text(debug_msg, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {e}")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /reset - reset l'état d'un user pour tests (admin only).

    Usage:
        /reset              - Reset momentum (comme nouveau)
        /reset momentum     - Reset momentum à 0
        /reset momentum 50  - Set momentum à 50
        /reset intimacy     - Reset intimacy history
        /reset day 3        - Set à jour 3
        /reset teasing 5    - Set teasing stage
        /reset paywall      - Reset paywall
        /reset all          - Full reset (supprime user)
    """
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return

    args = context.args
    target_telegram_id = update.effective_user.id  # Default: self

    # Check if first arg is a telegram_id
    if args and args[0].isdigit() and len(args[0]) > 5:
        target_telegram_id = int(args[0])
        args = args[1:]  # Remove from args

    try:
        pool = get_pool()

        if not args:
            # V3: Reset momentum state
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users SET
                        momentum = 0,
                        current_tier = 1,
                        messages_this_session = 0,
                        messages_since_climax = 999,
                        emotional_state = NULL
                    WHERE telegram_id = $1
                """, target_telegram_id)
            await update.message.reply_text(f"✅ Reset momentum pour {target_telegram_id}")
            return

        action = args[0].lower()

        if action == "momentum":
            # Reset or set momentum
            value = float(args[1]) if len(args) > 1 else 0
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET momentum = $1, messages_this_session = 0 WHERE telegram_id = $2",
                    value, target_telegram_id
                )
            await update.message.reply_text(f"✅ User {target_telegram_id} → Momentum {value:.1f}")

        elif action == "intimacy":
            # Reset intimacy history
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET intimacy_history = 0, messages_since_climax = 999 WHERE telegram_id = $1",
                    target_telegram_id
                )
            await update.message.reply_text(f"✅ User {target_telegram_id} → Intimacy history reset")

        elif action == "day" and len(args) > 1:
            day = int(args[1])
            from settings import PARIS_TZ
            from datetime import timedelta
            new_first_msg = datetime.now(PARIS_TZ) - timedelta(days=day - 1)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET first_message_at = $1 WHERE telegram_id = $2",
                    new_first_msg, target_telegram_id
                )
            await update.message.reply_text(f"✅ User {target_telegram_id} → Jour {day}")

        elif action == "tier" and len(args) > 1:
            # V3: Set tier directly (for testing)
            tier = int(args[1])
            # Set momentum to match tier
            tier_momentum = {1: 20, 2: 45, 3: 75}
            momentum = tier_momentum.get(tier, 20)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET current_tier = $1, momentum = $2 WHERE telegram_id = $3",
                    tier, momentum, target_telegram_id
                )
            tier_names = {1: "SFW", 2: "FLIRT", 3: "NSFW"}
            await update.message.reply_text(f"✅ User {target_telegram_id} → Tier {tier_names.get(tier, tier)} (momentum={momentum})")

        elif action == "teasing" and len(args) > 1:
            stage = int(args[1])
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET teasing_stage = $1 WHERE telegram_id = $2",
                    stage, target_telegram_id
                )
            await update.message.reply_text(f"✅ User {target_telegram_id} → Teasing stage {stage}")

        elif action == "paywall":
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users SET
                        paywall_sent = FALSE,
                        preparation_sent = FALSE,
                        conversion_shown_at = NULL,
                        premium_preview_count = 0
                    WHERE telegram_id = $1
                """, target_telegram_id)
            await update.message.reply_text(f"✅ Reset paywall pour {target_telegram_id}")

        elif action == "all":
            async with pool.acquire() as conn:
                # Delete user completely
                user = await conn.fetchrow(
                    "SELECT id FROM users WHERE telegram_id = $1", target_telegram_id
                )
                if user:
                    await conn.execute("DELETE FROM conversations_minimal WHERE user_id = $1", user["id"])
                    await conn.execute("DELETE FROM proactive_log WHERE user_id = $1", user["id"])
                    await conn.execute("DELETE FROM users WHERE id = $1", user["id"])
            await update.message.reply_text(f"✅ User {target_telegram_id} supprimé (full reset)")

        elif action == "cooldown":
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET cooldown_remaining = 0 WHERE telegram_id = $1",
                    target_telegram_id
                )
            await update.message.reply_text(f"✅ Cooldown reset pour {target_telegram_id}")

        elif action == "session":
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET messages_this_session = 0 WHERE telegram_id = $1",
                    target_telegram_id
                )
            await update.message.reply_text(f"✅ Session reset pour {target_telegram_id}")

        elif action == "mood" and len(args) > 1:
            # V8: Set Luna mood manually (for testing)
            new_mood = args[1].lower()
            valid_moods = ["normal", "playful", "tired", "romantic", "horny"]
            if new_mood not in valid_moods:
                await update.message.reply_text(f"❌ Mood invalide. Valides: {', '.join(valid_moods)}")
                return
            async with pool.acquire() as conn:
                if new_mood == "horny":
                    await conn.execute(
                        "UPDATE users SET luna_mood = $1, mood_updated_at = NOW(), last_horny_at = NOW() WHERE telegram_id = $2",
                        new_mood, target_telegram_id
                    )
                else:
                    await conn.execute(
                        "UPDATE users SET luna_mood = $1, mood_updated_at = NOW() WHERE telegram_id = $2",
                        new_mood, target_telegram_id
                    )
            await update.message.reply_text(f"✅ User {target_telegram_id} → Luna mood: {new_mood.upper()}")

        else:
            await update.message.reply_text("""❓ Usage:
/reset - Reset momentum (nouveau)
/reset momentum 50 - Set momentum
/reset intimacy - Reset intimacy history
/reset tier 2 - Set tier FLIRT
/reset day 3 - Set jour 3
/reset teasing 5 - Set teasing stage
/reset paywall - Reset paywall
/reset session - Reset session msgs
/reset mood playful - Set Luna mood
/reset all - Supprimer user""")

    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal avec tous les systèmes intégrés + V5 psychology."""
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

    logger.info(f"[{tg_user.first_name}] {user_text[:100]}...")

    # Track metrics
    metrics.record_message()

    # 1. Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # 2. Update last_active + last_message_at (persistant)
    last_msg_time = await get_last_message_time(user_id)
    hours_since_last = 0
    if last_msg_time:
        hours_since_last = (datetime.now(last_msg_time.tzinfo or None) - last_msg_time).total_seconds() / 3600

    await update_last_active(user_id)
    await set_last_message_time(user_id)

    # V5: Track sessions (nouvelle session si >4h d'inactivité)
    is_new_session = hours_since_last > 4
    if is_new_session:
        await increment_session_count(user_id)

    # 3. Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # 4. Incrémenter compteur
    msg_count = await increment_message_count(user_id)

    # 5. Récupérer données utilisateur complètes
    user_data = await get_user_data(user_id)
    first_message_at = user_data.get("first_message_at")

    # 6. Calculer phase et jour
    phase, day_count = get_relationship_phase(first_message_at)

    # 7. Vérifier subscription (paywall après 5 jours, sauf si abonné)
    subscription_status = user_data.get("subscription_status", "trial")
    if subscription_status != "active" and first_message_at and is_trial_expired(first_message_at):
        paywall_sent = await has_paywall_been_sent(user_id, get_pool())

        if not paywall_sent:
            paywall_msg = get_paywall_message(first_message_at, user_id)
            await update.message.reply_text(paywall_msg)
            await save_message(user_id, "assistant", paywall_msg)
            await mark_paywall_sent(user_id, get_pool())
            logger.info(f"Paywall envoyé à user {user_id}")
            return
        else:
            response = get_post_paywall_response()
            await update.message.reply_text(response)
            await save_message(user_id, "assistant", response)
            return

    # 8. Récupérer historique + mémoire
    history = await get_history(user_id)
    memory = await get_user_memory(user_id)

    # 9. Déterminer mood
    mood = get_current_mood()

    # 10. Get emotional state from DB (persistant)
    emotional_state = await get_emotional_state(user_id)

    # V5: Get psychology data
    psych_data = await get_psychology_data(user_id)
    existing_jokes = [InsideJoke.from_dict(j) for j in psych_data.get("inside_jokes", [])]
    pending_events = [PendingEvent.from_dict(e) for e in psych_data.get("pending_events", [])]

    logger.info(f"User {user_id}: Day={day_count}, Mood={mood}, Jokes={len(existing_jokes)}")

    # ============== V3: MOMENTUM SYSTEM ==============
    # Get current momentum state
    momentum_state = await get_momentum_state(user_id)
    current_momentum = momentum_state["momentum"]
    intimacy_history = momentum_state["intimacy_history"]
    messages_since_climax = momentum_state["messages_since_climax"]
    messages_this_session = momentum_state["messages_this_session"]
    last_message_at = momentum_state["last_message_at"]

    # V7: Apply time-based decay BEFORE calculating new momentum
    decayed_momentum = momentum_engine.apply_time_decay(
        current_momentum,
        last_message_at,
        messages_since_climax
    )
    if decayed_momentum != current_momentum:
        current_momentum = decayed_momentum

    # Classify message intensity and calculate new momentum
    new_momentum, intensity, is_negative_emotion = momentum_engine.calculate_momentum(
        user_text,
        current_momentum,
        messages_this_session,
        day_count
    )

    # V7: Apply SFW decay boost for faster return to normal after NSFW session
    sfw_boost = momentum_engine.get_sfw_decay_boost(intensity, messages_since_climax)
    if sfw_boost > 0:
        new_momentum = max(0, new_momentum - sfw_boost)

    # Check for climax in user message
    user_climax = False
    is_climax_msg = momentum_engine.detect_climax(user_text)
    if (intensity == Intensity.NSFW or current_momentum > 50) and is_climax_msg:
        user_climax = True
        new_momentum = momentum_engine.apply_climax_cooldown(new_momentum)
        logger.info(f"V3: User climax detected, momentum reduced to {new_momentum:.1f}")

    # Determine modifier based on state
    level_modifier = None

    # 1. Check emotional distress first
    if is_negative_emotion:
        level_modifier = "USER_DISTRESSED"
        logger.info("V3: Negative emotion detected, applying USER_DISTRESSED")

    # 2. Check recovery phase (after climax)
    elif user_climax:
        level_modifier = "AFTERCARE"
        messages_since_climax = 0  # Will be set after response
    elif messages_since_climax <= 3:
        level_modifier = momentum_engine.get_recovery_modifier(messages_since_climax)
        if level_modifier:
            logger.info(f"V3: Recovery phase, applying {level_modifier}")

    # 3. Apply soft caps based on phase
    elif not level_modifier:
        soft_cap = momentum_engine.apply_soft_cap(intensity, day_count, messages_this_session, new_momentum)
        if soft_cap.modifier:
            level_modifier = soft_cap.modifier
            logger.info(f"V3: Soft cap applied: {soft_cap.modifier}")

    # Get tier based on momentum
    tier = momentum_engine.get_tier(new_momentum, day_count, intimacy_history)

    logger.info(f"V3 Momentum: {current_momentum:.1f} → {new_momentum:.1f}, intensity={intensity.value}, tier={tier}")

    # ============== V8: LUNA MOOD SYSTEM ==============
    from settings import PARIS_TZ
    current_hour = datetime.now(PARIS_TZ).hour

    # Get mood state from DB
    mood_state = await get_mood_state(user_id)
    current_luna_mood = LunaMood(mood_state["luna_mood"])
    mood_updated_at = mood_state["mood_updated_at"]
    last_horny_at = mood_state["last_horny_at"]
    last_climax_at = mood_state["last_climax_at"]

    # Calculate hours since climax
    hours_since_climax = 999.0
    if last_climax_at:
        if last_climax_at.tzinfo is None:
            from datetime import timezone
            last_climax_at = last_climax_at.replace(tzinfo=timezone.utc)
        hours_since_climax = (datetime.now(last_climax_at.tzinfo) - last_climax_at).total_seconds() / 3600

    # Check if mood should be updated (every 2-4 hours)
    if luna_mood_engine.should_update_mood(mood_updated_at):
        new_luna_mood = luna_mood_engine.calculate_new_mood(
            current_luna_mood, last_horny_at, hours_since_climax, current_hour
        )
        if new_luna_mood != current_luna_mood:
            is_horny = new_luna_mood == LunaMood.HORNY
            await update_luna_mood(user_id, new_luna_mood.value, is_horny)
            current_luna_mood = new_luna_mood
            logger.info(f"V8: Luna mood updated to {new_luna_mood.value}")

    # Check availability for NSFW escalation (HOT or NSFW intensity)
    minutes_since_climax = hours_since_climax * 60
    is_escalating = intensity in (Intensity.HOT, Intensity.NSFW)
    availability_result = luna_mood_engine.check_availability(
        mood=current_luna_mood,
        minutes_since_climax=minutes_since_climax,
        current_hour=current_hour,
        momentum=new_momentum,
        intensity_is_nsfw=is_escalating
    )

    # Handle Luna initiates (JACKPOT!)
    luna_initiates = availability_result.luna_initiates
    should_deflect = availability_result.should_deflect
    deflect_type = availability_result.deflect_type

    if luna_initiates:
        logger.info(f"V8: JACKPOT! Luna initiates NSFW (mood={current_luna_mood.value})")
        level_modifier = "LUNA_INITIATES"
    elif should_deflect and tier >= 2:
        logger.info(f"V8: Deflecting NSFW attempt (type={deflect_type}, availability={availability_result.score:.2f})")
        level_modifier = f"DEFLECT_{deflect_type.upper()}" if deflect_type else "DEFLECT_PLAYFUL"
        # Force tier down when deflecting
        tier = min(tier, 2)

    # 11. Progress emotional state if user responded
    if emotional_state == "opener":
        await set_emotional_state(user_id, "follow_up")
        emotional_state = "follow_up"
    elif emotional_state == "follow_up":
        await set_emotional_state(user_id, "resolution")
        emotional_state = "resolution"
    elif emotional_state == "resolution":
        await set_emotional_state(user_id, None)
        emotional_state = None

    # V5: Intermittent reinforcement - get current state
    intermittent_state = intermittent.get_state(user_id, day_count, hours_since_last)
    affection_instruction = intermittent.get_affection_instruction(intermittent_state)

    # V5: Check for inside joke opportunities
    joke_opportunity = None
    if inside_jokes.should_create(day_count, len(existing_jokes)):
        joke_opportunity = inside_jokes.detect_opportunity(user_text, existing_jokes)
        if joke_opportunity:
            new_joke = inside_jokes.create_joke(joke_opportunity)
            existing_jokes.append(new_joke)
            await update_inside_jokes(user_id, [j.to_dict() for j in existing_jokes])
            logger.info(f"Created inside joke: {new_joke.value}")

    # V5: Extract pending events from user message
    new_events = memory_callbacks.extract_pending_events(user_text)
    if new_events:
        pending_events.extend(new_events)
        await update_pending_events(user_id, [e.to_dict() for e in pending_events])

    # V5: Check for vulnerability indicators
    vulnerability_words = ["j'ai peur", "je me sens seul", "j'avoue", "entre nous", "j'ai jamais dit"]
    if any(vw in user_text.lower() for vw in vulnerability_words):
        await increment_vulnerabilities(user_id)

    # 12. Check teasing opportunity (J2-5)
    teasing_msg = None
    if 2 <= day_count <= 5:
        teasing_msg = check_teasing_opportunity(day_count, user_data)
        if teasing_msg:
            await update_teasing_stage(user_id, user_data.get("teasing_stage", 0) + 1)

    # V5: Build extra instructions for LLM
    extra_instructions = []
    if affection_instruction:
        extra_instructions.append(affection_instruction)

    # V5: Memory callback instruction
    memory_instruction = memory_callbacks.get_memory_instruction(memory)
    if memory_instruction:
        extra_instructions.append(memory_instruction)

    # V5: Inside joke callback
    if existing_jokes and not joke_opportunity:
        for joke in existing_jokes:
            callback = inside_jokes.get_callback(joke, day_count)
            if callback:
                extra_instructions.append(f"\n## INSIDE JOKE\nMentionne naturellement: {callback}")
                joke.times_referenced += 1
                joke.last_referenced = datetime.now()
                await update_inside_jokes(user_id, [j.to_dict() for j in existing_jokes])
                break

    # ============== V3: LLM Router (Tier-based) ==============
    teasing_stage = user_data.get("teasing_stage", 0)
    subscription_status = user_data.get("subscription_status", "trial")

    # V3: Get provider and model based on momentum and tier
    provider, model, final_tier = get_llm_config_v3(
        momentum=new_momentum,
        day_count=day_count,
        intimacy_history=intimacy_history,
        subscription_status=subscription_status,
        detected_intensity=intensity,
        modifier=level_modifier
    )

    logger.info(f"V3 Router: provider={provider}, tier={final_tier}, modifier={level_modifier}")

    # V6: Track premium preview + check if conversion needed AFTER response
    show_conversion_after = False
    if is_premium_session(provider) and subscription_status != "active":
        preview_count = await conversion.increment_preview_count(user_id)
        logger.info(f"Premium preview count: {preview_count}")

        # Check if we should show conversion flow (but after responding)
        if await conversion.should_show_conversion(
            user_id, day_count, teasing_stage, subscription_status
        ):
            show_conversion_after = True

    # V7: Build system prompt based on tier with NSFW state support
    # Get user context for NSFW prompts
    user_name = (memory.get("prenom") if memory else None) or "lui"
    inside_jokes_list = [j.value for j in existing_jokes] if existing_jokes else []
    pet_names_list = (memory.get("pet_names") if memory else None) or []

    # Get NSFW state for tier 3
    nsfw_state = momentum_engine.get_nsfw_state(new_momentum, messages_since_climax)

    # V8: Handle deflect prompts and luna initiates
    if luna_initiates:
        system_prompt = get_luna_initiates_prompt()
        logger.info(f"V8: Using LUNA_INITIATES prompt (JACKPOT!)")
    elif should_deflect and deflect_type:
        system_prompt = get_deflect_prompt(deflect_type)
        logger.info(f"V8: Using DEFLECT prompt: {deflect_type}")
    # Use V7 prompt selector for tier 3, otherwise use regular
    elif final_tier >= 3:
        system_prompt = get_prompt_for_tier_v7(
            tier=final_tier,
            nsfw_state=nsfw_state,
            user_name=user_name,
            inside_jokes=inside_jokes_list,
            pet_names=pet_names_list,
            modifier=level_modifier
        )
        logger.info(f"V7 NSFW: state={nsfw_state}, user={user_name}")
    else:
        system_prompt = get_prompt_for_tier(final_tier, level_modifier)

    # 13. Générer réponse avec graceful fallback
    try:
        # Build messages for LLM
        messages = history.copy()
        messages.append({"role": "user", "content": user_text})

        # Add context to prompt
        from services.memory import format_memory_for_prompt
        from services.relationship import get_phase_instructions
        from services.mood import get_mood_instructions, get_mood_context

        prompt_parts = [system_prompt]
        if memory:
            prompt_parts.append(f"\n## CE QUE TU SAIS SUR LUI:\n{format_memory_for_prompt(memory)}")
        prompt_parts.append(get_phase_instructions(phase, day_count))
        prompt_parts.append(f"\n## TON HUMEUR:\n{get_mood_instructions(mood)}")
        if extra_instructions:
            prompt_parts.append(f"\n## INSTRUCTIONS:\n" + "\n".join(extra_instructions))

        full_prompt = "\n".join(prompt_parts)

        # Call with graceful fallback
        response = await call_with_graceful_fallback(
            messages=messages,
            system_prompt=full_prompt,
            provider=provider,
            model=model,
            tier=final_tier
        )
        metrics.record_llm_call(success=True)
    except Exception as e:
        metrics.record_llm_call(success=False)
        metrics.record_error(str(e))
        logger.error(f"LLM generation failed: {e}")
        response = "dsl j'ai bugé 😅"

    # V5: Modify response based on intermittent affection
    response = intermittent.modify_response(response, intermittent_state)

    # V5: Check variable rewards (skip during NSFW tier 3 to avoid awkward mix)
    if tier < 3:
        reward_context = RewardContext(
            user_id=user_id,
            phase=day_count,
            day_count=day_count,
            messages_this_session=msg_count % 50,  # Approximation
            user_message=user_text,
            memory=memory,
            conversation_sentiment="positive" if any(e in user_text.lower() for e in ["merci", "cool", "super", "j'aime"]) else "neutral"
        )
        reward = variable_rewards.check_reward(reward_context)
        if reward:
            reward_type, reward_msg = reward
            response = response + "\n\n" + reward_msg
            logger.info(f"Variable reward added: {reward_type.value}")

    # V5: Add inside joke creation message if opportunity
    if joke_opportunity:
        response = response + "\n\n" + joke_opportunity.creation_message

    # 14. Ajouter teasing si opportun
    if teasing_msg:
        response = response + "\n\n" + teasing_msg

    # 15. Sauvegarder réponse Luna
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # V3: Check for climax in Luna's response
    luna_climax = False
    if not user_climax and final_tier >= 3 and momentum_engine.detect_climax(response):
        luna_climax = True
        new_momentum = momentum_engine.apply_climax_cooldown(new_momentum)
        logger.info(f"V3: Luna climax detected, momentum reduced to {new_momentum:.1f}")

    # V3: Update momentum state
    if user_climax or luna_climax:
        # Start climax recovery (increments intimacy_history)
        await start_climax_recovery(user_id, new_momentum)
        logger.info(f"V3: Climax recovery started, intimacy_history incremented")
    else:
        # Normal momentum update
        await update_momentum_state(
            user_id=user_id,
            momentum=new_momentum,
            tier=final_tier,
            messages_this_session=messages_this_session + 1
        )

    # 16. Extraction mémoire périodique
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        try:
            logger.info(f"Extraction mémoire pour user {user_id} (msg #{msg_count})")
            updated_history = await get_history(user_id, limit=10)
            new_memory = await extract_memory(updated_history, memory)
            await update_user_memory(user_id, new_memory)
        except Exception as e:
            logger.error(f"Memory extraction failed for user {user_id}: {e}")

    # V5: Update attachment score periodically
    if msg_count % 10 == 0:
        try:
            # Récupérer les messages pour analyse
            all_history = await get_history(user_id, limit=50)
            user_messages_content = [m["content"] for m in all_history if m["role"] == "user"]

            score_data = {
                "user_messages": len([m for m in all_history if m["role"] == "user"]),
                "luna_messages": len([m for m in all_history if m["role"] == "assistant"]),
                "session_count": psych_data.get("session_count", 1),
                "user_initiated_count": psych_data.get("user_initiated_count", 0),
                "inside_jokes_count": len(existing_jokes),
                "vulnerabilities_shared": psych_data.get("vulnerabilities_shared", 0),
                "total_messages": msg_count,
                "user_messages_content": user_messages_content,
                "response_times": [],  # TODO: track response times
            }
            attachment_metrics = attachment_tracker.calculate_score(score_data)
            await update_attachment_score(user_id, attachment_metrics.score)
            logger.info(f"Attachment score updated: {attachment_metrics.score:.1f}")
        except Exception as e:
            logger.error(f"Attachment score update failed: {e}")

    # V6: Update teasing stage based on engagement signals
    engagement_increment = detect_engagement_signal(user_text)
    if engagement_increment > 0:
        new_teasing_stage = min(teasing_stage + engagement_increment, 8)
        if new_teasing_stage > teasing_stage:
            await update_teasing_stage(user_id, new_teasing_stage)
            logger.info(f"Teasing stage updated: {teasing_stage} -> {new_teasing_stage}")

    # 17. Envoyer avec délai naturel (+ intermittent delay modifier)
    delay_modifier = intermittent.get_delay_modifier(intermittent_state)
    await send_with_natural_delay(update, response, mood, delay_modifier)

    # V6: Show conversion flow AFTER response (not instead of)
    if show_conversion_after:
        await send_conversion_flow(update, context, user_id)


async def send_conversion_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Envoie le flow de conversion naturel vers l'abonnement."""
    import asyncio

    telegram_id = update.effective_user.id

    # Envoyer les messages de transition
    messages = conversion.get_transition_messages()

    for msg in messages:
        await asyncio.sleep(random.uniform(2, 4))
        await context.bot.send_chat_action(chat_id=telegram_id, action="typing")
        await asyncio.sleep(random.uniform(1, 2))
        await context.bot.send_message(chat_id=telegram_id, text=msg)
        await save_message(user_id, "assistant", msg)

    await asyncio.sleep(2)

    # Envoyer le CTA d'abonnement
    cta = conversion.get_cta()

    if PAYMENT_LINK:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(cta["button"], url=PAYMENT_LINK)]
        ])
        await context.bot.send_message(
            chat_id=telegram_id,
            text=cta["text"],
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(chat_id=telegram_id, text=cta["text"])

    # Marquer conversion montrée
    await conversion.mark_conversion_shown(user_id)
    logger.info(f"Conversion flow sent to user {user_id}")


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

            # 2b. V6: Check relance message (après conversion non payée)
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
    app.add_handler(CommandHandler("health", health_check))
    app.add_handler(CommandHandler("debug", debug_command))   # Admin: état interne
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

    logger.info("Luna GFE en ligne!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
