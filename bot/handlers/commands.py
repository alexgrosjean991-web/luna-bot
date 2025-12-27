"""
Command handlers for Luna Bot.

/start, /debug, /setpaid, /setday, /resetmsgs, /health
"""

from telegram import Update
from telegram.ext import ContextTypes

from core import get_logger
from config.settings import settings
from memory import (
    get_or_create_user as memory_get_or_create_user,
    get_user as memory_get_user,
    get_relationship,
    update_relationship,
)
from services.phases import Phase, get_current_phase, get_phase_progress
from services.nsfw_gate import NSFWGate
from services.engagement import EngagementState

logger = get_logger(__name__)


# =============================================================================
# DB HELPERS (will be moved to core/database.py later)
# =============================================================================

_pool = None


def set_pool(pool):
    """Set the database pool."""
    global _pool
    _pool = pool


async def get_or_create_user_with_context(telegram_id: int) -> tuple[dict, dict]:
    """Get or create user with relationship context."""
    user = await memory_get_or_create_user(telegram_id)
    relationship = await get_relationship(user["id"])
    return user, relationship


async def save_message(user_id, role: str, content: str):
    """Save a message."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_simple (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def load_nsfw_gate(user_id) -> NSFWGate:
    """Load NSFW gate from DB."""
    import json
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT nsfw_gate_data FROM memory_relationships WHERE user_id = $1
        """, user_id)

        if row and row["nsfw_gate_data"]:
            data = json.loads(row["nsfw_gate_data"]) if isinstance(row["nsfw_gate_data"], str) else row["nsfw_gate_data"]
            return NSFWGate.from_dict(data)
        return NSFWGate()


async def load_engagement_state(user_id) -> EngagementState:
    """Load engagement state from DB."""
    import json
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT engagement_state FROM memory_relationships WHERE user_id = $1
        """, user_id)

        if row and row["engagement_state"]:
            data = json.loads(row["engagement_state"]) if isinstance(row["engagement_state"], str) else row["engagement_state"]
            return EngagementState.from_dict(data)
        return EngagementState()


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start."""
    user, relationship = await get_or_create_user_with_context(update.effective_user.id)
    await update.message.reply_text("hey")
    await save_message(user["id"], "assistant", "hey")


async def handle_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /health - Bot health check."""
    await update.message.reply_text(f"Luna v{settings.BOT_VERSION} - OK")


async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug (admin only)."""
    if update.effective_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    user = await memory_get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("User not found")
        return

    relationship = await get_relationship(user["id"])

    # Load NSFW gate
    nsfw_gate = await load_nsfw_gate(user["id"])
    can_nsfw, gate_reason = nsfw_gate.check()

    # Load engagement state
    engagement = await load_engagement_state(user["id"])

    # Phase system info
    day = relationship.get('day', 1) if relationship else 1
    message_count = relationship.get('message_count', 0) if relationship else 0
    is_paid = relationship.get('paid', False) if relationship else False
    paywall_shown = relationship.get('paywall_shown', False) if relationship else False
    current_phase = get_current_phase(message_count, day, is_paid, paywall_shown)
    phase_progress = get_phase_progress(message_count, day)

    debug_info = f"""
Debug Info:
- Day: {day}
- Paid: {is_paid}

Phase System:
- Phase: {current_phase.value}
- Message count: {message_count}
- Paywall shown: {paywall_shown}
- Msgs to paywall: {phase_progress['msgs_to_paywall']}

Engagement (V7):
- Msgs since high reward: {engagement.reward.messages_since_reward}
- Reward streak: {engagement.reward.reward_streak}
- Photos today: {engagement.photo.photos_sent_today}
- Voices today: {engagement.voice.voices_sent_today}
- Proactives today: {engagement.proactive.proactives_today}

NSFW Gate (Phase LIBRE only):
- Can NSFW: {can_nsfw} ({gate_reason})
- Msgs since NSFW: {nsfw_gate.messages_since_nsfw}/20
- Sessions today: {nsfw_gate.nsfw_count_today}/2

User:
- Name: {user.get('name', 'Unknown')}
"""
    await update.message.reply_text(debug_info)


async def handle_setpaid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setpaid (admin only)."""
    if update.effective_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setpaid <telegram_id>")
        return

    target_id = int(args[0])
    user = await memory_get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    await update_relationship(user["id"], {"paid": True})
    await update.message.reply_text(f"User {target_id} marked as paid")


async def handle_setday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setday <day> (admin only)."""
    if update.effective_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setday <day> [telegram_id]")
        return

    target_day = int(args[0])
    target_id = int(args[1]) if len(args) > 1 else update.effective_user.id

    user = await memory_get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    async with _pool.acquire() as conn:
        old_day = await conn.fetchval(
            "SELECT day FROM memory_relationships WHERE user_id = $1",
            user["id"]
        )
        await conn.execute(
            "UPDATE memory_relationships SET day = $2 WHERE user_id = $1",
            user["id"], target_day
        )

    await update.message.reply_text(f"User {target_id}: Day {old_day} -> Day {target_day}")


async def handle_resetmsgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /resetmsgs [count] (admin only)."""
    if update.effective_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    args = context.args
    new_count = int(args[0]) if args else 0
    target_id = int(args[1]) if len(args) > 1 else update.effective_user.id

    user = await memory_get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET message_count = $2, paywall_shown = FALSE
            WHERE user_id = $1
        """, user["id"], new_count)

    current_phase = get_current_phase(new_count, 1, False, False)
    await update.message.reply_text(f"User {target_id}: message_count={new_count}, paywall_shown=False\nPhase: {current_phase.value}")
