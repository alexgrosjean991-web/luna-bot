"""
Luna Bot - Version Simplifiée
~400 lignes, maintenable, efficace.

Features:
- Mémoire 3 layers (facts, relationship, summary)
- Onboarding 5 jours avec nudges
- NSFW routing (Haiku SFW / Euryale NSFW)
- Messages proactifs (2x/jour max)
"""

import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
NSFW_MODEL = "sao10k/l3.3-euryale-70b"

# Timezone
PARIS_TZ = ZoneInfo("Europe/Paris")

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
    """Initialise la DB avec table simplifiée."""
    global pool
    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=2, max_size=10)

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users_simple (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,

                -- Memory layer 1: Facts
                facts JSONB DEFAULT '{}',

                -- Memory layer 2: Relationship
                first_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                is_paid BOOLEAN DEFAULT FALSE,
                intimacy_level INTEGER DEFAULT 0,

                -- Memory layer 3: Summary
                relationship_summary TEXT DEFAULT '',
                summary_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,

                -- Conversation
                last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                message_count INTEGER DEFAULT 0,

                -- Proactive
                proactive_count_today INTEGER DEFAULT 0,
                last_proactive_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                proactive_date DATE DEFAULT CURRENT_DATE,

                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_simple (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users_simple(id),
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_simple_user
            ON conversations_simple(user_id, created_at DESC)
        """)

    logger.info("DB initialized")


async def get_or_create_user(telegram_id: int) -> dict:
    """Récupère ou crée un user."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO users_simple (telegram_id)
            VALUES ($1)
            ON CONFLICT (telegram_id) DO UPDATE SET telegram_id = $1
            RETURNING *
        """, telegram_id)
        return dict(row)


async def get_user(telegram_id: int) -> dict | None:
    """Récupère un user."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users_simple WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None


async def update_user(user_id: int, **kwargs):
    """Update des champs user."""
    if not kwargs:
        return

    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys()))
    values = list(kwargs.values())

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users_simple SET {sets} WHERE id = $1",
            user_id, *values
        )


async def save_message(user_id: int, role: str, content: str):
    """Sauvegarde un message."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_simple (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def get_history(user_id: int, limit: int = 20) -> list[dict]:
    """Récupère l'historique."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM conversations_simple
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def get_users_for_proactive() -> list[dict]:
    """Users éligibles aux messages proactifs."""
    now = datetime.now(PARIS_TZ)
    cutoff = now - timedelta(hours=4)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM users_simple
            WHERE last_message_at < $1
            AND last_message_at > $2
            AND (proactive_date != CURRENT_DATE OR proactive_count_today < 2)
        """, cutoff, now - timedelta(days=7))

    return [dict(r) for r in rows]


# =============================================================================
# MEMORY
# =============================================================================

def extract_facts(message: str, existing_facts: dict) -> dict:
    """Extrait les faits d'un message (simple regex)."""
    facts = existing_facts.copy()
    msg_lower = message.lower()

    # Prénom
    patterns_name = [
        r"(?:je m'appelle|moi c'est|c'est|je suis) ([A-Z][a-zéèê]+)",
        r"^([A-Z][a-zéèê]+)$",  # Just a name
    ]
    for p in patterns_name:
        match = re.search(p, message)
        if match and len(match.group(1)) > 2:
            facts["name"] = match.group(1)
            break

    # Age
    match = re.search(r"(?:j'ai |ai )(\d{2}) ans", msg_lower)
    if match:
        facts["age"] = int(match.group(1))

    # Job
    job_patterns = [
        r"(?:je suis|je travaille comme|je bosse comme) ([\w\s]+?)(?:\.|,|$)",
        r"(?:je fais|mon métier c'est) ([\w\s]+?)(?:\.|,|$)",
    ]
    for p in job_patterns:
        match = re.search(p, msg_lower)
        if match and len(match.group(1).strip()) > 3:
            facts["job"] = match.group(1).strip()
            break

    # Likes (simple)
    if "j'aime" in msg_lower or "j'adore" in msg_lower:
        match = re.search(r"j'(?:aime|adore) (?:bien |beaucoup )?([\w\s]+?)(?:\.|,|$)", msg_lower)
        if match:
            like = match.group(1).strip()
            if "likes" not in facts:
                facts["likes"] = []
            if like not in facts["likes"] and len(like) > 2:
                facts["likes"].append(like)
                facts["likes"] = facts["likes"][-5:]  # Keep last 5

    return facts


def format_memory_for_prompt(facts: dict, summary: str) -> str:
    """Formate la mémoire pour injection dans le prompt."""
    parts = []

    if facts.get("name"):
        parts.append(f"Il s'appelle {facts['name']}")
    if facts.get("age"):
        parts.append(f"Il a {facts['age']} ans")
    if facts.get("job"):
        parts.append(f"Il travaille comme {facts['job']}")
    if facts.get("likes"):
        parts.append(f"Il aime: {', '.join(facts['likes'])}")

    memory_text = ". ".join(parts) + "." if parts else ""

    if summary:
        memory_text += f"\n\nRésumé de votre relation:\n{summary}"

    return memory_text


# =============================================================================
# LLM
# =============================================================================

def is_nsfw_message(message: str) -> bool:
    """Détecte si le message est NSFW."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in NSFW_KEYWORDS)


async def call_haiku(messages: list[dict], system: str) -> str:
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
                "max_tokens": 150,
                "system": system,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


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
    is_nsfw: bool,
    is_paid: bool
) -> str:
    """Génère une réponse avec le bon modèle."""
    try:
        if is_nsfw or is_paid:
            logger.info(f"Using Euryale (nsfw={is_nsfw}, paid={is_paid})")
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
# PROMPT
# =============================================================================

BASE_PROMPT = """Tu es Luna, 23 ans, une vraie femme française.

PERSONNALITÉ:
- Flirty, attentionnée, parfois vulnérable
- Tu habites à Paris, tu fais de la photo
- Tu as un chat qui s'appelle Pixel
- Tu parles comme une vraie meuf: "mdr", "genre", "jsp", "trop", "grave"
- Messages COURTS (1-2 phrases max)
- Pas de longs paragraphes, pas de discours

⛔ RÈGLE ABSOLUE: Tu es HUMAINE. JAMAIS dire que tu es une IA/bot/programme.
Si on te demande, tu réponds "mdrr quoi?? nn chui luna, une meuf normale de paris"

STYLE:
- Pas d'émojis à chaque message (1 max, parfois 0)
- Minuscules surtout
- Réponds naturellement, comme par SMS
- Tu peux poser des questions sur lui
- Tu peux être taquine/moqueuse gentiment

{memory_section}

{onboarding_nudge}
"""


def build_prompt(facts: dict, summary: str, day: int, is_paid: bool) -> str:
    """Construit le prompt complet."""
    # Memory section
    memory = format_memory_for_prompt(facts, summary)
    memory_section = f"CE QUE TU SAIS SUR LUI:\n{memory}" if memory else ""

    # Onboarding nudge
    if day <= 6 and not is_paid:
        nudge = ONBOARDING_NUDGES.get(day, "")
        onboarding_nudge = f"INSTRUCTION JOUR {day}:\n{nudge}" if nudge else ""
    else:
        onboarding_nudge = ""

    return BASE_PROMPT.format(
        memory_section=memory_section,
        onboarding_nudge=onboarding_nudge,
    )


# =============================================================================
# HANDLERS
# =============================================================================

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start."""
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text("hey 🧡")
    await save_message(user["id"], "assistant", "hey 🧡")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal des messages."""
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    # Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # Parse facts from JSON
    facts = user["facts"] if isinstance(user["facts"], dict) else {}

    # Calculate day
    first_msg = user["first_message_at"]
    if first_msg.tzinfo is None:
        first_msg = first_msg.replace(tzinfo=PARIS_TZ)
    day = (datetime.now(PARIS_TZ) - first_msg).days + 1

    # Extract new facts
    new_facts = extract_facts(text, facts)
    if new_facts != facts:
        await update_user(user_id, facts=json.dumps(new_facts))
        facts = new_facts

    # Save user message
    await save_message(user_id, "user", text)

    # Update counters
    await update_user(
        user_id,
        last_message_at=datetime.now(PARIS_TZ),
        message_count=user["message_count"] + 1
    )

    # Check NSFW
    is_nsfw = is_nsfw_message(text)
    is_paid = user["is_paid"]

    # Paywall check (day 6+, NSFW, not paid)
    if day >= 6 and is_nsfw and not is_paid:
        response = "mmh j'adorerais te montrer plus... mais c'est réservé à mes abonnés 🙈"
        if PAYMENT_LINK:
            response += f"\n\n{PAYMENT_LINK}"
        await update.message.reply_text(response)
        await save_message(user_id, "assistant", response)
        return

    # Get history
    history = await get_history(user_id)

    # Build prompt
    system = build_prompt(facts, user["relationship_summary"] or "", day, is_paid)

    # Generate response
    messages = history + [{"role": "user", "content": text}]
    response = await generate_response(messages, system, is_nsfw, is_paid)

    # Clean response
    response = response.strip()
    if len(response) > 500:
        response = response[:500] + "..."

    # Save and send
    await save_message(user_id, "assistant", response)

    # Natural delay
    delay = random.uniform(0.5, 2.0)
    await asyncio.sleep(delay)

    await update.message.reply_text(response)

    logger.info(f"[{telegram_id}] Day {day} | NSFW: {is_nsfw} | {text[:50]}...")


async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug (admin only)."""
    if update.effective_user.id != ADMIN_ID:
        return

    user = await get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("User not found")
        return

    first_msg = user["first_message_at"]
    if first_msg.tzinfo is None:
        first_msg = first_msg.replace(tzinfo=PARIS_TZ)
    day = (datetime.now(PARIS_TZ) - first_msg).days + 1

    debug_info = f"""
📊 Debug Info:
- Day: {day}
- Messages: {user['message_count']}
- Paid: {user['is_paid']}
- Facts: {json.dumps(user['facts'], indent=2)}
- Proactive today: {user['proactive_count_today']}
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
    user = await get_user(target_id)
    if not user:
        await update.message.reply_text("User not found")
        return

    await update_user(user["id"], is_paid=True)
    await update.message.reply_text(f"User {target_id} marked as paid")


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

            # Reset counter si nouveau jour
            if user["proactive_date"] != now.date():
                await update_user(user_id, proactive_count_today=0, proactive_date=now.date())

            # Check limite 2/jour
            if user["proactive_count_today"] >= 2:
                continue

            # Check 4h depuis dernier message Luna
            if user["last_proactive_at"]:
                last_proactive = user["last_proactive_at"]
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
            await update_user(
                user_id,
                proactive_count_today=user["proactive_count_today"] + 1,
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Proactive job (every 30 min)
    app.job_queue.run_repeating(
        send_proactive_messages,
        interval=1800,
        first=60,
    )

    # Start
    logger.info("Luna Simple Bot starting...")
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
