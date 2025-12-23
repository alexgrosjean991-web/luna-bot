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

# Constantes LLM Anthropic
LLM_MODEL = "claude-haiku-4-5-20251015"
MAX_TOKENS = 80           # Assez pour une réponse complète
HISTORY_LIMIT = 20
ANTHROPIC_API_VERSION = "2023-06-01"  # LOW FIX: API versioning

# OpenRouter (modèle premium)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PREMIUM_MODEL = "anthracite-org/magnum-v4-72b"
MAX_TOKENS_PREMIUM = 100  # 2-4 lignes style intime

# Conversion
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "")
TRIAL_DAYS = 5

# Bot version
BOT_VERSION = "1.1.0"  # V6: Multi-LLM + Conversion

# DB Pool
DB_POOL_MIN = 2
DB_POOL_MAX = 20
