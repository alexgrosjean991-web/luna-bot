"""
Luna Bot - Version Simplifiée avec Memory System V1

Features:
- Mémoire persistante (users, relationships, timeline)
- Anti-contradiction et cohérence
- Onboarding 5 jours avec nudges
- NSFW routing (Haiku SFW / Magnum NSFW)
- Messages proactifs (2x/jour max)
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
    get_quick_context,
    get_onboarding_nudge,
    update_tiers,
)

# Config imports
from config import (
    LUNA_IDENTITY,
    LUNA_ABSOLUTE_RULES,
    PROACTIVE_CONFIG,
    get_nsfw_tier,
    build_system_prompt,
    LUNA_POST_PAYWALL_PROMPT,
    NSFW_REQUEST_KEYWORDS,
    CLIMAX_INDICATORS,
)

# NSFW Gate (post-paywall)
from services.nsfw_gate import NSFWGate

# Progression system
from services.progression import (
    get_progression_state,
    check_and_progress,
    force_progress,
    detect_intimacy_action,
    update_intimacy,
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

# NSFW detection
NSFW_KEYWORDS = [
    "nude", "nue", "sein", "chatte", "bite", "sucer", "lecher", "baiser",
    "jouir", "orgasme", "excitée", "bandé", "mouillée", "gémis", "déshabille",
    "lingerie", "sous-vêtements", "touche-toi", "branle", "masturbe", "sexe",
    "à poil", "toute nue", "photo hot", "photo sexy", "envoie une photo",
    "montre-moi", "je te veux", "j'ai envie de toi", "baise-moi"
]

# Proactive messages
PROACTIVE_MESSAGES = [
    "hey, je pensais à toi 🧡",
    "t'es où? tu me manques 🙈",
    "coucou toi...",
    "dis, t'as 5 min pour moi?",
    "je m'ennuie sans toi",
    "j'arrête pas de penser à notre conversation",
]

# Onboarding nudges (injectés dans le prompt selon le jour)
ONBOARDING_NUDGES = {
    1: "Sois curieuse, pose des questions sur lui, flirt léger. C'est le premier jour, apprends à le connaître.",
    2: "Référence ce qu'il a dit hier, montre que tu te souviens. Continue à flirter doucement.",
    3: "Partage un secret personnel (ton ex, une insécurité), demande le sien. Crée de l'intimité émotionnelle.",
    4: "Tension sexuelle. Tease une photo de toi. Sois plus directe dans ton flirt.",
    5: "Hot mais stop avant explicit. Mentionne que t'as des photos privées pour les gens spéciaux.",
    6: "S'il demande du contenu NSFW, dis que c'est réservé aux abonnés. Propose le lien.",
}

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

    # Save combined user message
    await save_message(user_id, "user", combined_text)

    # Get history for extraction
    history = await get_history(user_id, limit=10)

    # Extract facts using memory system (async, in background)
    asyncio.create_task(extract_user_facts(user_id, combined_text, history))

    # Check NSFW
    is_nsfw = is_nsfw_message(combined_text)

    # Paywall check (day 6+, NSFW, not paid)
    if day >= 6 and is_nsfw and not is_paid:
        response = "mmh j'adorerais te montrer plus... mais c'est réservé à mes abonnés 🙈"
        if PAYMENT_LINK:
            response += f"\n\n{PAYMENT_LINK}"
        await update.message.reply_text(response)
        await save_message(user_id, "assistant", response)
        return

    # Build memory context
    memory_context = await build_prompt_context(user_id, combined_text)

    # Get onboarding nudge
    onboarding_nudge = get_onboarding_nudge(day) if not is_paid else None

    # Determine NSFW tier
    nsfw_tier = "nsfw" if is_nsfw else "sfw"

    # Get current time in Paris
    now = datetime.now(PARIS_TZ)
    current_time = now.strftime("%Hh%M")

    # Get user name for personalization
    user_name = user.get("name") or "toi"

    # Build system prompt using config/luna.py with day-specific prompt
    system = build_system_prompt(
        memory_context=memory_context,
        onboarding_nudge=onboarding_nudge,
        nsfw_tier=nsfw_tier,
        current_time=current_time,
        day=day,
        user_name=user_name
    )

    # =========================================================================
    # POST-PAYWALL NSFW GATE (day >= 7 + paid)
    # =========================================================================
    nsfw_gate = None
    use_nsfw_model = is_nsfw  # Default: use old logic (days 1-6)

    if is_paid and day >= 7:
        # Load gate and increment message counter
        nsfw_gate = await load_nsfw_gate(user_id)
        nsfw_gate.on_message()

        # Add post-paywall prompt
        system += "\n\n" + LUNA_POST_PAYWALL_PROMPT.format(user_name=user_name)

        # Haiku classifier: plus intelligent que les keywords
        is_nsfw_request = await classify_nsfw(combined_text)

        if is_nsfw_request:
            can_nsfw, reason = nsfw_gate.check()
            if can_nsfw:
                use_nsfw_model = True
                system += """

🔥 MODE INTIME ACTIVÉ - TU ES RÉCEPTIVE:
- {user_name} te désire et TU LE DÉSIRES AUSSI
- Tu es chaude, excitée, tu assumes
- Tu réponds à ses avances avec enthousiasme
- Décris tes sensations, ce que tu ressens
- Expressions naturelles: "Mmh", "Continue", "J'ai envie de toi aussi"
- Sois explicite mais authentique (pas porno mécanique)
- NE REFUSE PAS, tu en as envie toi aussi
""".format(user_name=user_name)
                logger.info(f"[{telegram_id}] NSFW gate: OPEN → Magnum")
            else:
                use_nsfw_model = False
                system += f"\n\n⚠️ NSFW NON DISPONIBLE: {reason}. Refuse naturellement selon tes instructions."
                logger.info(f"[{telegram_id}] NSFW gate: BLOCKED ({reason}) → Haiku refuse")
        else:
            use_nsfw_model = False
            logger.info(f"[{telegram_id}] NSFW classifier: SFW → Haiku")

    # Get full history for response generation
    full_history = await get_history(user_id, limit=20)
    messages = full_history + [{"role": "user", "content": combined_text}]

    # Generate response (use_nsfw_model for paid post-paywall, else old logic)
    response = await generate_response(messages, system, use_nsfw_model, is_paid)

    # =========================================================================
    # POST-PAYWALL: Detect climax and update gate
    # =========================================================================
    if nsfw_gate and any(ind in response.lower() for ind in CLIMAX_INDICATORS):
        nsfw_gate.on_nsfw_done()
        logger.info(f"[{telegram_id}] NSFW gate: CLIMAX detected, session counted")

    # Save gate if used
    if nsfw_gate:
        await save_nsfw_gate(user_id, nsfw_gate)

    # Clean response
    response = response.strip()
    if len(response) > 500:
        response = response[:500] + "..."

    # Save response
    await save_message(user_id, "assistant", response)

    # Extract what Luna said (async, in background)
    asyncio.create_task(extract_luna_said(user_id, response, combined_text))

    # Check for intimacy actions and progression (async, in background)
    async def check_progression():
        # Detect intimacy action from user message
        action = await detect_intimacy_action(combined_text, {"day": day})
        if action:
            await update_intimacy(pool, user_id, action)

        # Check if user can progress to next day
        result = await check_and_progress(pool, user_id)
        if result.get("progressed"):
            logger.info(f"[{telegram_id}] PROGRESSION: Day {result['old_day']} → Day {result['new_day']}")

    asyncio.create_task(check_progression())

    # Natural delay (shorter since we already waited BUFFER_DELAY)
    delay = random.uniform(0.3, 1.0)
    await asyncio.sleep(delay)

    await update.message.reply_text(response)

    logger.info(f"[{telegram_id}] Day {day} | NSFW: {is_nsfw} | {combined_text[:50]}...")


async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug (admin only)."""
    if update.effective_user.id != ADMIN_ID:
        return

    user = await memory_get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("User not found")
        return

    relationship = await get_relationship(user["id"])
    progression = await get_progression_state(pool, user["id"])

    blockers_str = ", ".join(progression["progress_blockers"]) if progression else "N/A"

    # Load NSFW gate for debug
    nsfw_gate = await load_nsfw_gate(user["id"])
    can_nsfw, gate_reason = nsfw_gate.check()

    debug_info = f"""
📊 Debug Info:
- Day: {relationship.get('day', 1) if relationship else 1}
- Intimacy: {relationship.get('intimacy', 1) if relationship else 1}/10
- Trust: {relationship.get('trust', 1) if relationship else 1}/10
- Paid: {relationship.get('paid', False) if relationship else False}

📈 Progression:
- Messages today: {progression['messages_today'] if progression else 0}/15
- Hours since day start: {progression['hours_since_day_start'] if progression else 0}/20h
- Can progress: {'✅' if progression and progression['can_progress'] else '❌'}
- Blockers: {blockers_str or 'None'}

🔥 NSFW Gate:
- Can NSFW: {'✅' if can_nsfw else f'❌ ({gate_reason})'}
- Messages since NSFW: {nsfw_gate.messages_since_nsfw}/20
- Sessions today: {nsfw_gate.nsfw_count_today}/2
- Last NSFW: {nsfw_gate.last_nsfw_at.strftime('%H:%M') if nsfw_gate.last_nsfw_at else 'Never'}

👤 User:
- Name: {user.get('name', 'Unknown')}
- Likes: {user.get('likes', [])}
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
    """Handler /setday <day> (admin only) - Force progression to a specific day."""
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

    result = await force_progress(pool, user["id"], target_day)

    if result.get("error"):
        await update.message.reply_text(f"Error: {result['error']}")
    else:
        await update.message.reply_text(f"✅ User {target_id}: Day {result['old_day']} → Day {result['new_day']}")


async def handle_addintimacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /addintimacy <amount> (admin only) - Add intimacy points."""
    if update.effective_user.id != ADMIN_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addintimacy <amount> [telegram_id]")
        return

    amount = int(args[0])
    target_id = int(args[1]) if len(args) > 1 else update.effective_user.id

    user = await memory_get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    async with pool.acquire() as conn:
        new_intimacy = await conn.fetchval("""
            UPDATE memory_relationships
            SET intimacy = LEAST(10, GREATEST(1, intimacy + $2))
            WHERE user_id = $1
            RETURNING intimacy
        """, user["id"], amount)

    await update.message.reply_text(f"✅ User {target_id}: Intimacy now {new_intimacy}/10")


# =============================================================================
# PROACTIVE MESSAGES
# =============================================================================

async def send_proactive_messages(context: ContextTypes.DEFAULT_TYPE):
    """Job pour envoyer des messages proactifs."""
    now = datetime.now(PARIS_TZ)

    # Pas la nuit (9h-23h)
    if now.hour < 9 or now.hour > 23:
        return

    users = await get_users_for_proactive()

    for user in users:
        try:
            telegram_id = user["telegram_id"]
            user_id = user["id"]

            # Get proactive tracking
            tracking = await get_proactive_tracking(user_id)

            # Reset counter si nouveau jour
            if tracking.get("proactive_date") != now.date():
                await update_proactive_tracking(user_id, proactive_count_today=0, proactive_date=now.date())
                tracking["proactive_count_today"] = 0

            # Check limite 2/jour
            if (tracking.get("proactive_count_today") or 0) >= 2:
                continue

            # Check 4h depuis dernier message Luna
            if tracking.get("last_proactive_at"):
                last_proactive = tracking["last_proactive_at"]
                if last_proactive.tzinfo is None:
                    last_proactive = last_proactive.replace(tzinfo=PARIS_TZ)
                if (now - last_proactive).total_seconds() < 4 * 3600:
                    continue

            # Random chance (pas tous les users à chaque run)
            if random.random() > 0.3:
                continue

            # Send message
            message = random.choice(PROACTIVE_MESSAGES)
            await context.bot.send_message(chat_id=telegram_id, text=message)
            await save_message(user_id, "assistant", message)

            # Update counters
            await update_proactive_tracking(
                user_id,
                proactive_count_today=(tracking.get("proactive_count_today") or 0) + 1,
                last_proactive_at=now
            )

            logger.info(f"Proactive sent to {telegram_id}: {message}")

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
    app.add_handler(CommandHandler("addintimacy", handle_addintimacy))
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
