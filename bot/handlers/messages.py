"""
Message handler for Luna Bot.

Main conversation logic.
"""

import asyncio
import json
import random
import re
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from core import get_logger
from core.errors import get_natural_error
from config.settings import settings, NSFW_KEYWORDS, CLIMAX_PATTERNS
from memory import (
    get_or_create_user as memory_get_or_create_user,
    get_relationship,
    extract_unified,
    build_prompt_context,
)
from services.phases import Phase, get_current_phase, get_paywall_message
from services.nsfw_gate import NSFWGate
from services.engagement import VariableRewards, EngagementState, JealousyHandler
from prompts.luna import build_system_prompt

logger = get_logger(__name__)


# =============================================================================
# MODULE STATE
# =============================================================================

_pool = None
message_buffers: dict[int, list[str]] = {}
buffer_tasks: dict[int, asyncio.Task] = {}


def set_pool(pool):
    """Set database pool for this module."""
    global _pool
    _pool = pool


# =============================================================================
# VALIDATION PATTERNS
# =============================================================================

RESPONSE_FACT_PATTERNS = [
    (r"tu\s+(?:t'appelles?|es)\s+(\w+)", "name"),
    (r"tu\s+(?:travailles?|bosses?)\s+(?:comme|en tant que)\s+(\w+)", "job"),
    (r"tu\s+(?:habites?|vis?)\s+(?:à|a)\s+(\w+)", "location"),
]

COMMON_WORDS_TO_IGNORE = {
    "quoi", "comment", "pourquoi", "bien", "mal", "trop", "très", "super",
    "moi", "toi", "lui", "elle", "nous", "vous", "tout", "rien",
}

LUNA_FACTS = {
    "jobs": {"graphiste", "designer", "ui", "ux", "freelance"},
    "locations": {"paris", "11", "11ème", "11e", "oberkampf"},
}


# =============================================================================
# DB HELPERS
# =============================================================================

async def get_or_create_user_with_context(telegram_id: int) -> tuple[dict, dict]:
    """Get or create user with relationship."""
    user = await memory_get_or_create_user(telegram_id)
    relationship = await get_relationship(user["id"])
    return user, relationship


async def save_message(user_id, role: str, content: str):
    """Save message to DB."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_simple (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def get_history(user_id, limit: int = 20) -> list[dict]:
    """Get conversation history."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM conversations_simple
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def increment_message_count(user_id) -> int:
    """Increment message count."""
    async with _pool.acquire() as conn:
        return await conn.fetchval("""
            UPDATE memory_relationships
            SET message_count = COALESCE(message_count, 0) + 1
            WHERE user_id = $1
            RETURNING message_count
        """, user_id)


async def mark_paywall_shown(user_id):
    """Mark paywall as shown."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships SET paywall_shown = TRUE WHERE user_id = $1
        """, user_id)


async def load_nsfw_gate(user_id) -> NSFWGate:
    """Load NSFW gate."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT nsfw_gate_data FROM memory_relationships WHERE user_id = $1
        """, user_id)
        if row and row["nsfw_gate_data"]:
            data = json.loads(row["nsfw_gate_data"]) if isinstance(row["nsfw_gate_data"], str) else row["nsfw_gate_data"]
            return NSFWGate.from_dict(data)
    return NSFWGate()


async def save_nsfw_gate(user_id, gate: NSFWGate):
    """Save NSFW gate."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships SET nsfw_gate_data = $2 WHERE user_id = $1
        """, user_id, json.dumps(gate.to_dict()))


async def load_engagement_state(user_id) -> EngagementState:
    """Load engagement state."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT engagement_state FROM memory_relationships WHERE user_id = $1
        """, user_id)
        if row and row["engagement_state"]:
            data = json.loads(row["engagement_state"]) if isinstance(row["engagement_state"], str) else row["engagement_state"]
            return EngagementState.from_dict(data)
    return EngagementState()


async def save_engagement_state(user_id, state: EngagementState):
    """Save engagement state."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships SET engagement_state = $2 WHERE user_id = $1
        """, user_id, json.dumps(state.to_dict()))


# =============================================================================
# HELPERS
# =============================================================================

def create_safe_task(coro, task_name: str):
    """Create async task with error handling."""
    async def wrapped():
        try:
            return await coro
        except Exception as e:
            logger.error(f"[{task_name}] Task failed: {e}", exc_info=True)
            return None
    return asyncio.create_task(wrapped())


def is_nsfw_message(message: str) -> bool:
    """Check if message contains NSFW keywords."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in NSFW_KEYWORDS)


async def validate_response_facts(response: str, user_facts: dict) -> tuple[str, list[str]]:
    """Validate Luna doesn't hallucinate facts."""
    warnings = []
    response_lower = response.lower()

    user_name = (user_facts.get("name") or "").lower()
    user_job = (user_facts.get("job") or "").lower()
    user_location = (user_facts.get("location") or "").lower()

    for pattern, fact_type in RESPONSE_FACT_PATTERNS:
        matches = re.finditer(pattern, response_lower)
        for match in matches:
            if not match.lastindex:
                continue
            mentioned = match.group(1).lower()

            if mentioned in COMMON_WORDS_TO_IGNORE:
                continue
            if fact_type == "job" and mentioned in LUNA_FACTS["jobs"]:
                continue
            if fact_type == "location" and mentioned in LUNA_FACTS["locations"]:
                continue

            if fact_type == "name" and user_name and mentioned != user_name:
                warnings.append(f"HALLUCINATION: name '{mentioned}' vs '{user_name}'")
            elif fact_type == "job" and user_job and mentioned not in user_job:
                warnings.append(f"HALLUCINATION: job '{mentioned}' vs '{user_job}'")

    for w in warnings:
        logger.warning(w)

    return response, warnings


# =============================================================================
# LLM CALLS
# =============================================================================

async def call_haiku(messages: list[dict], system: str, max_tokens: int = 150) -> str:
    """Call Claude Haiku."""
    import httpx
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.HAIKU_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            },
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]


async def call_magnum(messages: list[dict], system: str) -> str:
    """Call Magnum via OpenRouter."""
    import httpx
    formatted = [{"role": "system", "content": system}]
    for m in messages:
        formatted.append({"role": m["role"], "content": m["content"]})

    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.MAGNUM_MODEL,
                "max_tokens": 200,
                "messages": formatted,
                "temperature": 0.8,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def classify_nsfw(message: str) -> bool:
    """Classify if message is NSFW using Haiku."""
    try:
        response = await call_haiku(
            messages=[{"role": "user", "content": message}],
            system="""Tu es un classificateur. Réponds UNIQUEMENT 'YES' ou 'NO'.
Ce message a-t-il une intention sexuelle/NSFW? Sois LARGE dans ton interprétation.
EN CAS DE DOUTE -> YES""",
            max_tokens=5
        )
        return "YES" in response.upper()
    except Exception as e:
        logger.error(f"NSFW classifier error: {e}")
        return False


async def generate_response(messages: list[dict], system: str, use_nsfw: bool) -> str:
    """Generate response with appropriate model."""
    try:
        if use_nsfw:
            logger.info("Using Magnum (NSFW)")
            return await call_magnum(messages, system)
        else:
            logger.info("Using Haiku (SFW)")
            return await call_haiku(messages, system)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return get_natural_error()


# =============================================================================
# MAIN HANDLER
# =============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler - buffers messages before responding."""
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    # Add to buffer
    if telegram_id not in message_buffers:
        message_buffers[telegram_id] = []
    message_buffers[telegram_id].append(text)

    # Cancel previous task
    if telegram_id in buffer_tasks:
        buffer_tasks[telegram_id].cancel()

    # Create delayed processing task
    async def delayed_process():
        delay = 0.1 if settings.TEST_MODE else settings.BUFFER_DELAY
        await asyncio.sleep(delay)
        await process_buffered_messages(telegram_id, update, context)

    buffer_tasks[telegram_id] = asyncio.create_task(delayed_process())


async def process_buffered_messages(telegram_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process all buffered messages."""
    # Get and clear buffer
    messages_list = message_buffers.pop(telegram_id, [])
    buffer_tasks.pop(telegram_id, None)

    if not messages_list:
        return

    # Dedupe consecutive identical messages
    deduped = []
    for msg in messages_list:
        if not deduped or msg.lower() != deduped[-1].lower():
            deduped.append(msg)

    combined_text = " ".join(deduped) if len(deduped) > 1 else deduped[0]
    logger.info(f"[{telegram_id}] Buffered {len(messages_list)} -> {len(deduped)} msgs")

    # Get user context
    user, relationship = await get_or_create_user_with_context(telegram_id)
    user_id = user["id"]
    day = (relationship or {}).get("day", 1)
    is_paid = (relationship or {}).get("paid", False)
    paywall_shown = (relationship or {}).get("paywall_shown", False)

    # Increment message count
    message_count = await increment_message_count(user_id)

    # Save user message
    await save_message(user_id, "user", combined_text)

    # Get phase
    current_phase = get_current_phase(message_count, day, is_paid, paywall_shown)
    logger.info(f"[{telegram_id}] Phase: {current_phase.value} (msg={message_count})")

    # Check NSFW
    is_nsfw = is_nsfw_message(combined_text)

    # PAYWALL PHASE
    if current_phase == Phase.PAYWALL and not paywall_shown:
        user_name = user.get("name") or "babe"
        paywall_msg = get_paywall_message(user_name)
        if settings.PAYMENT_LINK:
            paywall_msg += f"\n\n{settings.PAYMENT_LINK}"
        await update.message.reply_text(paywall_msg)
        await save_message(user_id, "assistant", paywall_msg)
        await mark_paywall_shown(user_id)
        logger.info(f"[{telegram_id}] PAYWALL TRIGGERED")
        return

    # Build memory context
    memory_context = await build_prompt_context(user_id, combined_text)

    # Current time
    now = datetime.now(settings.TIMEZONE)
    current_time = now.strftime("%Hh%M")

    # User name
    user_name = user.get("name")

    # Engagement system
    engagement = await load_engagement_state(user_id)

    # Variable rewards
    affection_level = VariableRewards.get_affection_level(engagement.reward, current_phase.value)
    affection_modifier = VariableRewards.get_modifier(affection_level)
    VariableRewards.update_state(engagement.reward, affection_level)

    # Jealousy
    jealousy_modifier = None
    if JealousyHandler.detect(combined_text):
        jealousy_modifier = JealousyHandler.get_modifier(current_phase.value)
        logger.info(f"[{telegram_id}] Jealousy detected")

    mood_override = affection_modifier
    if jealousy_modifier:
        mood_override += f"\n\nJALOUSIE: {jealousy_modifier}"

    # NSFW gate (LIBRE phase only)
    nsfw_gate = None
    use_nsfw_model = False
    nsfw_allowed = False
    nsfw_blocked_reason = None

    if current_phase == Phase.LIBRE:
        nsfw_gate = await load_nsfw_gate(user_id)
        nsfw_gate.on_message()

        if is_nsfw:
            is_nsfw_request = await classify_nsfw(combined_text)
            if is_nsfw_request:
                can_nsfw, reason = nsfw_gate.check()
                if can_nsfw:
                    use_nsfw_model = True
                    nsfw_allowed = True
                    logger.info(f"[{telegram_id}] NSFW gate: OPEN")
                else:
                    nsfw_blocked_reason = reason
                    logger.info(f"[{telegram_id}] NSFW gate: BLOCKED ({reason})")

    # Build prompt
    system = build_system_prompt(
        phase=current_phase.value,
        user_name=user_name,
        memory_context=memory_context,
        current_time=current_time,
        nsfw_allowed=nsfw_allowed,
        nsfw_blocked_reason=nsfw_blocked_reason,
        mood=mood_override,
    )

    # Get history and generate
    history = await get_history(user_id, limit=20)
    messages = history + [{"role": "user", "content": combined_text}]
    response = await generate_response(messages, system, use_nsfw_model)

    # Detect climax
    if nsfw_gate and any(p in response.lower() for p in CLIMAX_PATTERNS):
        nsfw_gate.on_nsfw_done()
        logger.info(f"[{telegram_id}] CLIMAX detected")

    # Save states
    if nsfw_gate:
        await save_nsfw_gate(user_id, nsfw_gate)
    await save_engagement_state(user_id, engagement)

    # Clean response
    response = response.strip()
    if len(response) > 500:
        response = response[:500] + "..."

    # Validate
    response, warnings = await validate_response_facts(response, user)

    # Save and send
    await save_message(user_id, "assistant", response)

    # Extract memory in background
    history_short = await get_history(user_id, limit=10)
    create_safe_task(
        extract_unified(user_id, combined_text, response, history_short),
        "extract_unified"
    )

    # Natural delay
    if not settings.TEST_MODE:
        await asyncio.sleep(random.uniform(0.3, 1.0))

    await update.message.reply_text(response)

    logger.info(f"[{telegram_id}] Phase: {current_phase.value} | Affection: {affection_level} | NSFW: {is_nsfw}")
