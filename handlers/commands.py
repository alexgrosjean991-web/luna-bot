"""Command handlers for Luna Bot (/start, /health, /debug, /reset)."""
import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

from settings import BOT_VERSION, ADMIN_TELEGRAM_ID, PARIS_TZ
from services.db import (
    get_or_create_user, save_message, get_pool,
    reset_momentum, reset_intimacy_history
)
from services.momentum import momentum_engine
from middleware.metrics import metrics
from middleware.rate_limit import rate_limiter


# Health check file for Docker
HEALTH_FILE = "/tmp/luna_health"
BOT_START_TIME = datetime.now()


def write_health_file() -> None:
    """Ecrit un fichier health pour Docker."""
    try:
        with open(HEALTH_FILE, "w") as f:
            f.write(str(datetime.now().timestamp()))
    except Exception as e:
        logger.warning(f"Failed to write health file: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start."""
    user = await get_or_create_user(update.effective_user.id)
    welcome = "salut :) t'es qui toi?"
    await save_message(user["id"], "assistant", welcome)
    await update.message.reply_text(welcome)


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /health - verifie l'etat du bot."""
    try:
        # Verifier la DB
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "OK"
    except Exception as e:
        db_status = f"ERROR: {e}"

    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Get metrics
    stats = metrics.get_stats()

    health_msg = f"""Health Check

**Bot**: Running (v{BOT_VERSION})
**DB**: {db_status}
**Uptime**: {hours}h {minutes}m {seconds}s

**Metrics**:
- Messages: {stats['messages_processed']}
- LLM calls: {stats['llm_calls']} (success: {stats['llm_success_rate']})
- Errors: {stats['errors_count']}
- Rate limiter: {len(rate_limiter._requests)} users
"""
    if stats['last_error']:
        health_msg += f"\nLast error: {stats['last_error'][:50]}"

    await update.message.reply_text(health_msg, parse_mode="Markdown")


def is_admin(user_id: int) -> bool:
    """Verifie si l'utilisateur est admin (ADMIN_TELEGRAM_ID doit etre configure)."""
    return ADMIN_TELEGRAM_ID != 0 and user_id == ADMIN_TELEGRAM_ID


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /debug - affiche l'etat interne d'un user (admin only)."""
    if not is_admin(update.effective_user.id):
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
            await update.message.reply_text(f"User {target_telegram_id} non trouve")
            return

        # Calculate day_count
        first_msg = user.get("first_message_at")
        if first_msg:
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

        debug_msg = f"""**Debug User {target_telegram_id}**

**Etat General**
- Messages: {user.get('total_messages', 0)}
- Jour: J{day_count}
- Phase: {user.get('phase', 'discovery')}
- Subscription: {user.get('subscription_status', 'trial')}

**Momentum (V7)**
- Momentum: {momentum:.1f}/100
- Tier actuel: {tier_str}
- Etat NSFW: {nsfw_state_str}
- Intimacy history: {intimacy} sessions NSFW
- Msgs depuis climax: {msgs_since_climax}
- Msgs cette session: {user.get('messages_this_session', 0)}

**Luna Mood (V8)**
- Mood actuel: {luna_mood.upper()}
- Derniere MAJ: {mood_updated or 'jamais'}
- Dernier horny: {last_horny or 'jamais'}

**Engagement**
- Teasing stage: {user.get('teasing_stage', 0)}/8
- Emotional state: {user.get('emotional_state') or 'None'}
- Attachment score: {user.get('attachment_score', 0):.1f}/100
- Premium previews: {user.get('premium_preview_count', 0)}

**Memoire**
{memory_str[:200]}

**Timestamps**
- First msg: {user.get('first_message_at')}
- Last active: {user.get('last_active')}
- Paywall sent: {user.get('paywall_sent', False)}
"""
        await update.message.reply_text(debug_msg, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Erreur: {e}")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /reset - reset l'etat d'un user pour tests (admin only).

    Usage:
        /reset              - Reset momentum (comme nouveau)
        /reset momentum     - Reset momentum a 0
        /reset momentum 50  - Set momentum a 50
        /reset intimacy     - Reset intimacy history
        /reset day 3        - Set a jour 3
        /reset teasing 5    - Set teasing stage
        /reset paywall      - Reset paywall
        /reset all          - Full reset (supprime user)
    """
    if not is_admin(update.effective_user.id):
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
            await update.message.reply_text(f"Reset momentum pour {target_telegram_id}")
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
            await update.message.reply_text(f"User {target_telegram_id} -> Momentum {value:.1f}")

        elif action == "intimacy":
            # Reset intimacy history
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET intimacy_history = 0, messages_since_climax = 999 WHERE telegram_id = $1",
                    target_telegram_id
                )
            await update.message.reply_text(f"User {target_telegram_id} -> Intimacy history reset")

        elif action == "day" and len(args) > 1:
            day = int(args[1])
            from datetime import timedelta
            new_first_msg = datetime.now(PARIS_TZ) - timedelta(days=day - 1)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET first_message_at = $1 WHERE telegram_id = $2",
                    new_first_msg, target_telegram_id
                )
            await update.message.reply_text(f"User {target_telegram_id} -> Jour {day}")

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
            await update.message.reply_text(f"User {target_telegram_id} -> Tier {tier_names.get(tier, tier)} (momentum={momentum})")

        elif action == "teasing" and len(args) > 1:
            stage = int(args[1])
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET teasing_stage = $1 WHERE telegram_id = $2",
                    stage, target_telegram_id
                )
            await update.message.reply_text(f"User {target_telegram_id} -> Teasing stage {stage}")

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
            await update.message.reply_text(f"Reset paywall pour {target_telegram_id}")

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
            await update.message.reply_text(f"User {target_telegram_id} supprime (full reset)")

        elif action == "session":
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET messages_this_session = 0 WHERE telegram_id = $1",
                    target_telegram_id
                )
            await update.message.reply_text(f"Session reset pour {target_telegram_id}")

        elif action == "mood" and len(args) > 1:
            # V8: Set Luna mood manually (for testing)
            new_mood = args[1].lower()
            valid_moods = ["normal", "playful", "tired", "romantic", "horny"]
            if new_mood not in valid_moods:
                await update.message.reply_text(f"Mood invalide. Valides: {', '.join(valid_moods)}")
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
            await update.message.reply_text(f"User {target_telegram_id} -> Luna mood: {new_mood.upper()}")

        else:
            await update.message.reply_text("""Usage:
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
        await update.message.reply_text(f"Erreur: {e}")
