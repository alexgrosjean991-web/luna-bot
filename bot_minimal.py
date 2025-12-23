"""
Luna Bot - Version Minimale avec Persistance DB
"""

import os
import logging
import asyncio
import httpx
import asyncpg
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "172.18.0.2"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "luna"),
    "password": os.getenv("DB_PASSWORD", "luna_password"),
    "database": os.getenv("DB_NAME", "luna_db")
}

# Charger le prompt
PROMPT_FILE = Path(__file__).parent / "prompt.txt"
SYSTEM_PROMPT = PROMPT_FILE.read_text(encoding="utf-8")

# DB pool global
db_pool = None


async def init_db():
    """Initialise la connexion DB et crée la table si nécessaire"""
    global db_pool

    db_pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_minimal (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_user
            ON conversations_minimal(user_id, created_at DESC)
        """)

    logger.info("DB connectée")


async def get_history(user_id: int, limit: int = 20) -> list:
    """Récupère l'historique depuis la DB"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM conversations_minimal
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)

    # Reverse pour avoir l'ordre chronologique
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def save_message(user_id: int, role: str, content: str):
    """Sauvegarde un message dans la DB"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO conversations_minimal (user_id, role, content)
            VALUES ($1, $2, $3)
        """, user_id, role, content)


async def call_haiku(system_prompt: str, messages: list) -> str:
    """Appel simple à Claude Haiku"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 100,
        "system": system_prompt,
        "messages": messages[-20:]
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Erreur Haiku: {e}")
        return "dsl j'ai bugé 😅"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal"""

    user = update.effective_user
    user_id = user.id
    user_text = update.message.text

    if not user_text:
        return

    logger.info(f"[{user.first_name}] {user_text}")

    # Récupérer l'historique depuis la DB
    history = await get_history(user_id)

    # Ajouter le message user
    history.append({"role": "user", "content": user_text})

    # Sauvegarder le message user
    await save_message(user_id, "user", user_text)

    # Appeler Haiku
    response = await call_haiku(SYSTEM_PROMPT, history)

    # Sauvegarder la réponse
    await save_message(user_id, "assistant", response)

    logger.info(f"[Luna] {response}")

    # Envoyer
    await update.message.reply_text(response)


async def post_init(application):
    """Appelé après le démarrage de l'application"""
    await init_db()


def main():
    """Démarrer le bot"""

    logger.info("Démarrage Luna Bot (avec persistance DB)...")

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Luna est en ligne!")
    app.run_polling()


if __name__ == "__main__":
    main()
