"""Configuration centralisée."""
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Timezone Paris (gère automatiquement heure d'été/hiver)
PARIS_TZ = ZoneInfo("Europe/Paris")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN manquant dans .env")

# Database
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "172.18.0.2"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "luna"),
    "password": os.getenv("DB_PASSWORD", "luna_password"),
    "database": os.getenv("DB_NAME", "luna_db")
}

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY manquant dans .env")

# Constantes LLM
LLM_MODEL = "claude-3-5-haiku-20241022"
MAX_TOKENS = 40           # Réduit pour forcer réponses courtes
HISTORY_LIMIT = 20

# DB Pool
DB_POOL_MIN = 2
DB_POOL_MAX = 20
