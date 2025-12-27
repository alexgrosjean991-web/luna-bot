"""
Luna Bot - LLM-First Architecture

Philosophy: "Luna est libre, le code pose les rails."

Features:
- Phase system: HOOK → CONNECT → ATTACH → TENSION → PAYWALL → LIBRE
- Memory system (extraction + retrieval)
- NSFW routing (Haiku SFW / Magnum NSFW for LIBRE phase)
- Proactive messages (2x/day max)
"""

import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Memory system imports
from memory import (
    set_pool as set_memory_pool,
    set_extraction_api_key,
    init_memory_tables,
    get_or_create_user as memory_get_or_create_user,
    get_user as memory_get_user,
    get_relationship,
    update_relationship,
    extract_user_facts,
    extract_luna_said,
    build_prompt_context,
    update_tiers,
)

# NSFW Gate (post-paywall)
from services.nsfw_gate import NSFWGate

# Phase system
from services.phases import (
    Phase,
    get_current_phase,
    get_phase_progress,
    get_paywall_message,
    maybe_increment_day,
)

# Prompt builder
from prompts.luna import build_system_prompt

# Engagement engine (V7)
from services.engagement import (
    VariableRewards,
    EngagementState,
    JealousyHandler,
    ProactiveEngine,
)

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "luna"),
    "password": os.getenv("DB_PASSWORD", "luna_password"),
    "database": os.getenv("DB_NAME", "luna_db"),
}

# Models
HAIKU_MODEL = "claude-haiku-4-5-20251001"
NSFW_MODEL = "anthracite-org/magnum-v4-72b"

# Timezone
PARIS_TZ = ZoneInfo("Europe/Paris")

# Message batching
BUFFER_DELAY = 3.5  # secondes avant de répondre (laisse l'user finir)
message_buffers: dict[int, list[str]] = {}  # telegram_id -> [messages]
buffer_tasks: dict[int, asyncio.Task] = {}  # telegram_id -> pending task

# NSFW detection - keywords first pass (fast, free), then Haiku confirms
NSFW_KEYWORDS = [
    "nude", "nue", "nu", "sein", "chatte", "bite", "sucer", "lecher", "baiser",
    "jouir", "orgasme", "excitée", "bandé", "mouillée", "gémis", "déshabille",
    "lingerie", "string", "culotte", "touche-toi", "branle", "masturbe", "sexe",
    "à poil", "toute nue", "photo hot", "photo sexy", "montre-moi", "je te veux",
    "j'ai envie de toi", "baise-moi", "suce", "queue", "téton"
]

# Climax detection patterns (for NSFW gate)
CLIMAX_PATTERNS = [
    "j'ai joui", "je jouis", "je viens de jouir",
    "je tremble encore", "je tremble de partout",
    "c'était incroyable", "putain c'était bon",
]

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE
# =============================================================================

pool: asyncpg.Pool | None = None


async def init_db():
    """Initialise la DB avec tables mémoire."""
    global pool
    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=2, max_size=10)

    # Init memory system pool
    set_memory_pool(pool)
    set_extraction_api_key(OPENROUTER_API_KEY)

    # Init memory tables
    await init_memory_tables(pool)

    # Keep conversations table for history
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_simple (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES memory_users(id),
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_simple_user
            ON conversations_simple(user_id, created_at DESC)
        """)

        # Add nsfw_gate_data column if not exists
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS nsfw_gate_data JSON DEFAULT NULL
        """)

        # Phase system columns
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0
        """)

        # Engagement state (V7)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS engagement_state JSON DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS paywall_shown BOOLEAN DEFAULT FALSE
        """)

        # Proactive tracking table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_tracking (
                user_id UUID PRIMARY KEY REFERENCES memory_users(id),
                proactive_count_today INTEGER DEFAULT 0,
                last_proactive_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                proactive_date DATE DEFAULT CURRENT_DATE
            )
        """)

    logger.info("DB initialized with memory system")


async def get_or_create_user_with_context(telegram_id: int) -> tuple[dict, dict]:
    """Récupère ou crée un user avec son contexte."""
    user = await memory_get_or_create_user(telegram_id)
    relationship = await get_relationship(user["id"])
    return user, relationship


async def get_proactive_tracking(user_id) -> dict:
    """Récupère le tracking proactif d'un user."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO proactive_tracking (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO UPDATE SET user_id = $1
            RETURNING *
        """, user_id)
        return dict(row) if row else {}


async def update_proactive_tracking(user_id, **kwargs):
    """Update le tracking proactif."""
    if not kwargs:
        return

    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys()))
    values = list(kwargs.values())

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE proactive_tracking SET {sets} WHERE user_id = $1",
            user_id, *values
        )


async def save_message(user_id, role: str, content: str):
    """Sauvegarde un message (user_id est un UUID)."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_simple (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def get_history(user_id, limit: int = 20) -> list[dict]:
    """Récupère l'historique (user_id est un UUID)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM conversations_simple
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def load_nsfw_gate(user_id) -> NSFWGate:
    """Charge le NSFW gate d'un user depuis la DB."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT nsfw_gate_data FROM memory_relationships WHERE user_id = $1
        """, user_id)

        if row and row["nsfw_gate_data"]:
            import json
            data = json.loads(row["nsfw_gate_data"]) if isinstance(row["nsfw_gate_data"], str) else row["nsfw_gate_data"]
            return NSFWGate.from_dict(data)
        return NSFWGate()


async def save_nsfw_gate(user_id, gate: NSFWGate):
    """Sauvegarde le NSFW gate en DB."""
    import json
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET nsfw_gate_data = $2
            WHERE user_id = $1
        """, user_id, json.dumps(gate.to_dict()))


async def load_engagement_state(user_id) -> EngagementState:
    """Charge l'engagement state depuis la DB."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT engagement_state FROM memory_relationships WHERE user_id = $1
        """, user_id)

        if row and row["engagement_state"]:
            data = json.loads(row["engagement_state"]) if isinstance(row["engagement_state"], str) else row["engagement_state"]
            return EngagementState.from_dict(data)
        return EngagementState()


async def save_engagement_state(user_id, state: EngagementState):
    """Sauvegarde l'engagement state en DB."""
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET engagement_state = $2
            WHERE user_id = $1
        """, user_id, json.dumps(state.to_dict()))


async def increment_message_count(user_id) -> int:
    """Incrémente le compteur de messages et retourne la nouvelle valeur."""
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            UPDATE memory_relationships
            SET message_count = COALESCE(message_count, 0) + 1
            WHERE user_id = $1
            RETURNING message_count
        """, user_id)


async def mark_paywall_shown(user_id):
    """Marque le paywall comme affiché."""
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET paywall_shown = TRUE
            WHERE user_id = $1
        """, user_id)


async def get_users_for_proactive() -> list[dict]:
    """Users éligibles aux messages proactifs."""
    now = datetime.now(PARIS_TZ)
    cutoff = now - timedelta(hours=4)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.*, r.day, r.paid, p.proactive_count_today, p.last_proactive_at, p.proactive_date
            FROM memory_users u
            JOIN memory_relationships r ON r.user_id = u.id
            LEFT JOIN proactive_tracking p ON p.user_id = u.id
            WHERE u.updated_at < $1
            AND u.updated_at > $2
            AND (p.proactive_date IS NULL OR p.proactive_date != CURRENT_DATE OR p.proactive_count_today < 2)
        """, cutoff, now - timedelta(days=7))

    return [dict(r) for r in rows]


# =============================================================================
# MEMORY (uses memory/ module)
# =============================================================================

# Memory extraction is now handled by memory/extraction.py
# Memory retrieval is now handled by memory/retrieval.py


# =============================================================================
# LLM
# =============================================================================

def is_nsfw_message(message: str) -> bool:
    """Détecte si le message est NSFW."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in NSFW_KEYWORDS)


async def call_haiku(messages: list[dict], system: str, max_tokens: int = 150) -> str:
    """Appel Claude Haiku."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": HAIKU_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


async def classify_nsfw(message: str) -> bool:
    """
    Haiku classifie si le message est une demande NSFW.
    Plus intelligent que les keywords - comprend le contexte.
    """
    try:
        response = await call_haiku(
            messages=[{"role": "user", "content": message}],
            system="""Tu es un classificateur PERMISSIF. Réponds UNIQUEMENT 'YES' ou 'NO'.

Ce message a-t-il une intention sexuelle/NSFW? Sois LARGE dans ton interprétation.

YES si:
- Demande de nude, photo, déshabillage (même avec fautes: "nud", "nu", "envoie photo")
- Questions sur les sous-vêtements ("string", "culotte", "soutif")
- "j'ai envie de toi", "je te veux", "je bande", "je mouille"
- Demandes explicites même mal écrites
- Flirt sexuel même subtil
- Tout ce qui parle du corps de façon sexuelle

NO seulement si:
- Conversation 100% normale sans aucune allusion
- Compliments innocents style "t'es belle"

EN CAS DE DOUTE → YES

Réponds UNIQUEMENT: YES ou NO""",
            max_tokens=5
        )
        is_nsfw = "YES" in response.upper()
        logger.info(f"NSFW classifier: '{message[:30]}...' → {is_nsfw}")
        return is_nsfw
    except Exception as e:
        logger.error(f"NSFW classifier error: {e}")
        return False  # Safe default


async def call_euryale(messages: list[dict], system: str) -> str:
    """Appel Euryale via OpenRouter."""
    # Format messages for OpenRouter (OpenAI format)
    formatted = [{"role": "system", "content": system}]
    for m in messages:
        formatted.append({"role": m["role"], "content": m["content"]})

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NSFW_MODEL,
                "max_tokens": 200,
                "messages": formatted,
                "temperature": 0.8,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def generate_response(
    messages: list[dict],
    system: str,
    use_nsfw_model: bool,
    is_paid: bool = False  # Kept for backwards compat but ignored in V7+
) -> str:
    """Génère une réponse avec le bon modèle."""
    try:
        if use_nsfw_model:
            logger.info("Using Magnum (NSFW)")
            return await call_euryale(messages, system)
        else:
            logger.info("Using Haiku (SFW)")
            return await call_haiku(messages, system)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return random.choice([
            "désolée j'ai bugué 2 sec",
            "attends j'ai pas capté",
            "pardon je déconnecte, tu disais?",
        ])


# =============================================================================
# PROMPT (uses config/luna.py)
# =============================================================================

# Prompt building is now handled by config/luna.py
# See: build_system_prompt(), LUNA_IDENTITY, LUNA_ABSOLUTE_RULES


# =============================================================================
# HANDLERS
# =============================================================================

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start."""
    user, relationship = await get_or_create_user_with_context(update.effective_user.id)
    await update.message.reply_text("hey 🧡")
    await save_message(user["id"], "assistant", "hey 🧡")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal - buffer les messages avant de répondre."""
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    # Ajouter au buffer
    if telegram_id not in message_buffers:
        message_buffers[telegram_id] = []
    message_buffers[telegram_id].append(text)

    # Annuler la task précédente si elle existe
    if telegram_id in buffer_tasks:
        buffer_tasks[telegram_id].cancel()

    # Créer une nouvelle task qui attend BUFFER_DELAY avant de process
    async def delayed_process():
        await asyncio.sleep(BUFFER_DELAY)
        await process_buffered_messages(telegram_id, update, context)

    buffer_tasks[telegram_id] = asyncio.create_task(delayed_process())


async def process_buffered_messages(telegram_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process tous les messages bufferisés."""
    # Récupérer et vider le buffer
    messages_list = message_buffers.pop(telegram_id, [])
    buffer_tasks.pop(telegram_id, None)

    if not messages_list:
        return

    # Dédupliquer les messages identiques consécutifs (spam)
    deduped = []
    for msg in messages_list:
        if not deduped or msg.lower() != deduped[-1].lower():
            deduped.append(msg)

    # Combiner les messages
    if len(deduped) == 1:
        combined_text = deduped[0]
    else:
        combined_text = " ".join(deduped)

    logger.info(f"[{telegram_id}] Buffered {len(messages_list)} msgs → {len(deduped)} deduped")

    # Get/create user with memory system
    user, relationship = await get_or_create_user_with_context(telegram_id)
    user_id = user["id"]
    day = relationship.get("day", 1) if relationship else 1
    is_paid = relationship.get("paid", False) if relationship else False
    paywall_shown = relationship.get("paywall_shown", False) if relationship else False

    # Increment message count (new phase system)
    message_count = await increment_message_count(user_id)

    # Save combined user message
    await save_message(user_id, "user", combined_text)

    # Get history for extraction
    history = await get_history(user_id, limit=10)

    # Extract facts using memory system (async, in background)
    asyncio.create_task(extract_user_facts(user_id, combined_text, history))

    # =========================================================================
    # PHASE SYSTEM (replaces old day-based logic)
    # =========================================================================
    current_phase = get_current_phase(message_count, day, is_paid, paywall_shown)
    logger.info(f"[{telegram_id}] Phase: {current_phase.value} (msg={message_count}, day={day})")

    # Check NSFW
    is_nsfw = is_nsfw_message(combined_text)

    # PAYWALL PHASE: Trigger conversion
    if current_phase == Phase.PAYWALL and not paywall_shown:
        user_name = user.get("name") or "bébé"
        paywall_msg = get_paywall_message(user_name)
        if PAYMENT_LINK:
            paywall_msg += f"\n\n{PAYMENT_LINK}"
        await update.message.reply_text(paywall_msg)
        await save_message(user_id, "assistant", paywall_msg)
        await mark_paywall_shown(user_id)
        logger.info(f"[{telegram_id}] PAYWALL TRIGGERED (day={day}, msgs={message_count})")
        return

    # TENSION phase + NSFW request: Tease but don't give (pre-paywall frustration)
    if current_phase == Phase.TENSION and is_nsfw and not is_paid:
        # Continue to process but prompt will handle the teasing
        pass

    # Build memory context
    memory_context = await build_prompt_context(user_id, combined_text)

    # Get current time in Paris
    now = datetime.now(PARIS_TZ)
    current_time = now.strftime("%Hh%M")

    # Get user name for personalization
    user_name = user.get("name") or None

    # =========================================================================
    # ENGAGEMENT SYSTEM (V7)
    # =========================================================================
    engagement = await load_engagement_state(user_id)

    # Get affection level (variable rewards)
    affection_level = VariableRewards.get_affection_level(engagement.reward, current_phase.value)
    affection_modifier = VariableRewards.get_modifier(affection_level)
    VariableRewards.update_state(engagement.reward, affection_level)

    # Check for jealousy trigger
    jealousy_modifier = None
    if JealousyHandler.detect(combined_text):
        jealousy_modifier = JealousyHandler.get_modifier(current_phase.value)
        logger.info(f"[{telegram_id}] Jealousy detected: {current_phase.value}")

    # Combine modifiers for mood override
    mood_override = affection_modifier
    if jealousy_modifier:
        mood_override += f"\n\nJALOUSIE: {jealousy_modifier}"

    # =========================================================================
    # NSFW DETECTION & GATE (Phase LIBRE only)
    # =========================================================================
    nsfw_gate = None
    use_nsfw_model = False
    nsfw_allowed = False
    nsfw_blocked_reason = None

    if current_phase == Phase.LIBRE:
        # Load gate and increment message counter
        nsfw_gate = await load_nsfw_gate(user_id)
        nsfw_gate.on_message()

        # Two-pass NSFW detection: keywords first (free), then Haiku confirms
        if is_nsfw:
            is_nsfw_request = await classify_nsfw(combined_text)
            if is_nsfw_request:
                can_nsfw, reason = nsfw_gate.check()
                if can_nsfw:
                    use_nsfw_model = True
                    nsfw_allowed = True
                    logger.info(f"[{telegram_id}] NSFW gate: OPEN → Magnum")
                else:
                    nsfw_blocked_reason = reason
                    logger.info(f"[{telegram_id}] NSFW gate: BLOCKED ({reason}) → Haiku")
            else:
                logger.info(f"[{telegram_id}] NSFW classifier: SFW → Haiku")
        else:
            logger.info(f"[{telegram_id}] No NSFW keywords → Haiku")

    # Build system prompt using NEW UNIFIED BUILDER
    system = build_system_prompt(
        phase=current_phase.value,
        user_name=user_name,
        memory_context=memory_context,
        current_time=current_time,
        nsfw_allowed=nsfw_allowed,
        nsfw_blocked_reason=nsfw_blocked_reason,
        mood=mood_override,  # V7: Variable rewards + jealousy
    )

    # Get full history for response generation
    full_history = await get_history(user_id, limit=20)
    messages = full_history + [{"role": "user", "content": combined_text}]

    # Generate response (use_nsfw_model for paid post-paywall, else old logic)
    response = await generate_response(messages, system, use_nsfw_model, is_paid)

    # =========================================================================
    # POST-PAYWALL: Detect climax and update gate
    # =========================================================================
    if nsfw_gate and any(pattern in response.lower() for pattern in CLIMAX_PATTERNS):
        nsfw_gate.on_nsfw_done()
        logger.info(f"[{telegram_id}] NSFW gate: CLIMAX detected, session counted")

    # Save gate if used
    if nsfw_gate:
        await save_nsfw_gate(user_id, nsfw_gate)

    # Save engagement state (V7)
    await save_engagement_state(user_id, engagement)

    # Clean response
    response = response.strip()
    if len(response) > 500:
        response = response[:500] + "..."

    # Save response
    await save_message(user_id, "assistant", response)

    # Extract what Luna said (async, in background)
    asyncio.create_task(extract_luna_said(user_id, response, combined_text))

    # Natural delay (shorter since we already waited BUFFER_DELAY)
    delay = random.uniform(0.3, 1.0)
    await asyncio.sleep(delay)

    await update.message.reply_text(response)

    logger.info(f"[{telegram_id}] Phase: {current_phase.value} | Day {day} | Msgs: {message_count} | Affection: {affection_level} | NSFW: {is_nsfw}")


async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug (admin only)."""
    if update.effective_user.id != ADMIN_ID:
        return

    user = await memory_get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("User not found")
        return

    relationship = await get_relationship(user["id"])

    # Load NSFW gate for debug
    nsfw_gate = await load_nsfw_gate(user["id"])
    can_nsfw, gate_reason = nsfw_gate.check()

    # Load engagement state (V7)
    engagement = await load_engagement_state(user["id"])

    # Phase system info
    day = relationship.get('day', 1) if relationship else 1
    message_count = relationship.get('message_count', 0) if relationship else 0
    is_paid = relationship.get('paid', False) if relationship else False
    paywall_shown = relationship.get('paywall_shown', False) if relationship else False
    current_phase = get_current_phase(message_count, day, is_paid, paywall_shown)
    phase_progress = get_phase_progress(message_count, day)

    debug_info = f"""
📊 Debug Info:
- Day: {day}
- Paid: {is_paid}

🎯 Phase System:
- Phase: {current_phase.value}
- Message count: {message_count}
- Paywall shown: {paywall_shown}
- Msgs to paywall: {phase_progress['msgs_to_paywall']}
- Days to paywall: {phase_progress['days_to_paywall']}
- Paywall ready: {'✅' if phase_progress['paywall_ready'] else '❌'}

🎰 Engagement (V7):
- Msgs since high reward: {engagement.reward.messages_since_reward}
- Reward streak: {engagement.reward.reward_streak}
- Photos today: {engagement.photo.photos_sent_today}
- Voices today: {engagement.voice.voices_sent_today}
- Proactives today: {engagement.proactive.proactives_today}

🔥 NSFW Gate (Phase LIBRE only):
- Can NSFW: {'✅' if can_nsfw else f'❌ ({gate_reason})'}
- Msgs since NSFW: {nsfw_gate.messages_since_nsfw}/20
- Sessions today: {nsfw_gate.nsfw_count_today}/2

👤 User:
- Name: {user.get('name', 'Unknown')}
"""
    await update.message.reply_text(debug_info)


async def handle_setpaid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setpaid (admin only)."""
    if update.effective_user.id != ADMIN_ID:
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
    """Handler /setday <day> (admin only) - Force day to a specific value."""
    if update.effective_user.id != ADMIN_ID:
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

    async with pool.acquire() as conn:
        old_day = await conn.fetchval(
            "SELECT day FROM memory_relationships WHERE user_id = $1",
            user["id"]
        )
        await conn.execute(
            "UPDATE memory_relationships SET day = $2 WHERE user_id = $1",
            user["id"], target_day
        )

    await update.message.reply_text(f"✅ User {target_id}: Day {old_day} → Day {target_day}")


async def handle_resetmsgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /resetmsgs [count] (admin only) - Reset message count for phase testing."""
    if update.effective_user.id != ADMIN_ID:
        return

    args = context.args
    new_count = int(args[0]) if args else 0
    target_id = int(args[1]) if len(args) > 1 else update.effective_user.id

    user = await memory_get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE memory_relationships
            SET message_count = $2, paywall_shown = FALSE
            WHERE user_id = $1
        """, user["id"], new_count)

    current_phase = get_current_phase(new_count, 1, False, False)
    await update.message.reply_text(f"✅ User {target_id}: message_count={new_count}, paywall_shown=False\nPhase: {current_phase.value}")


# =============================================================================
# PROACTIVE MESSAGES
# =============================================================================

async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE):
    """Job pour envoyer des messages proactifs (V7: uses ProactiveEngine)."""
    now = datetime.now(PARIS_TZ)

    # Pas la nuit (9h-23h)
    if now.hour < 9 or now.hour > 23:
        return

    users = await get_users_for_proactive()

    for user in users:
        try:
            telegram_id = user["telegram_id"]
            user_id = user["id"]
            user_name = user.get("name")
            day = user.get("day", 1)
            is_paid = user.get("paid", False)
            message_count = user.get("message_count", 0) or 0

            # Get current phase
            current_phase = get_current_phase(message_count, day, is_paid, False)

            # Load engagement state
            engagement = await load_engagement_state(user_id)

            # Calculate hours since last user message
            updated_at = user.get("updated_at")
            if updated_at:
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=PARIS_TZ)
                hours_since_last = (now - updated_at).total_seconds() / 3600
            else:
                hours_since_last = 0

            # V7: Use ProactiveEngine to decide
            proactive_context = ProactiveEngine.should_send(
                state=engagement.proactive,
                phase=current_phase.value,
                hours_since_last_user_msg=hours_since_last,
                message_count=message_count,
            )

            if not proactive_context:
                continue

            # Get message from engine
            message = ProactiveEngine.get_message(proactive_context, user_name)

            # Send
            await context.bot.send_message(chat_id=telegram_id, text=message)
            await save_message(user_id, "assistant", message)

            # Update state
            ProactiveEngine.update_state(engagement.proactive)
            await save_engagement_state(user_id, engagement)

            logger.info(f"Proactive ({proactive_context}) sent to {telegram_id}: {message}")

        except Exception as e:
            logger.error(f"Proactive error for user {user['id']}: {e}")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Point d'entrée principal."""
    # Init DB
    await init_db()

    # Create application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("debug", handle_debug))
    app.add_handler(CommandHandler("setpaid", handle_setpaid))
    app.add_handler(CommandHandler("setday", handle_setday))
    app.add_handler(CommandHandler("resetmsgs", handle_resetmsgs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Proactive job (every 30 min)
    app.job_queue.run_repeating(
        send_proactive_messages,
        interval=1800,
        first=60,
    )

    # Memory tier update job (every hour)
    async def update_memory_tiers(context):
        try:
            count = await update_tiers()
            if count:
                logger.info(f"Memory tiers updated: {count} events")
        except Exception as e:
            logger.error(f"Tier update error: {e}")

    app.job_queue.run_repeating(
        update_memory_tiers,
        interval=3600,  # 1 hour
        first=300,
    )

    # Start
    logger.info("Luna Simple Bot with Memory V1 starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        if pool:
            await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
