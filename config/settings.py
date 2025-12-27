"""
Centralized configuration for Luna Bot.

All environment variables and constants in one place.

Usage:
    from config.settings import settings
    print(settings.TELEGRAM_TOKEN)
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    """Get env var with default."""
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    """Get env var as int."""
    return int(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    """Get env var as bool."""
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


def _env_list(key: str, default: str = "", sep: str = ",") -> list[str]:
    """Get env var as list."""
    val = os.getenv(key, default)
    return [x.strip() for x in val.split(sep) if x.strip()]


@dataclass
class Settings:
    """Luna Bot configuration."""

    # =========================================================================
    # TELEGRAM
    # =========================================================================
    TELEGRAM_TOKEN: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    ADMIN_TELEGRAM_ID: int = field(default_factory=lambda: _env_int("ADMIN_TELEGRAM_ID", 0))

    # =========================================================================
    # DATABASE
    # =========================================================================
    DB_HOST: str = field(default_factory=lambda: _env("DB_HOST", "localhost"))
    DB_PORT: int = field(default_factory=lambda: _env_int("DB_PORT", 5432))
    DB_USER: str = field(default_factory=lambda: _env("DB_USER", "luna"))
    DB_PASSWORD: str = field(default_factory=lambda: _env("DB_PASSWORD", "luna_password"))
    DB_NAME: str = field(default_factory=lambda: _env("DB_NAME", "luna_db"))
    DB_POOL_MIN: int = field(default_factory=lambda: _env_int("DB_POOL_MIN", 2))
    DB_POOL_MAX: int = field(default_factory=lambda: _env_int("DB_POOL_MAX", 10))

    @property
    def DB_CONFIG(self) -> dict:
        """Get DB config dict for asyncpg."""
        return {
            "host": self.DB_HOST,
            "port": self.DB_PORT,
            "user": self.DB_USER,
            "password": self.DB_PASSWORD,
            "database": self.DB_NAME,
        }

    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    OPENROUTER_API_KEY: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))

    # Models
    HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    MAGNUM_MODEL: str = "anthracite-org/magnum-v4-72b"

    # LLM settings
    LLM_TIMEOUT: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 30))
    LLM_MAX_RETRIES: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 3))

    # =========================================================================
    # PAYMENTS
    # =========================================================================
    PAYMENT_LINK: str = field(default_factory=lambda: _env("PAYMENT_LINK", ""))
    MOONPAY_API_KEY: str = field(default_factory=lambda: _env("MOONPAY_API_KEY", ""))
    MOONPAY_WEBHOOK_SECRET: str = field(default_factory=lambda: _env("MOONPAY_WEBHOOK_SECRET", ""))

    # =========================================================================
    # PHOTOS
    # =========================================================================
    PHOTOS_PATH: str = field(default_factory=lambda: _env("PHOTOS_PATH", "/app/content/photos"))

    # =========================================================================
    # LOGGING
    # =========================================================================
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    LOG_JSON: bool = field(default_factory=lambda: _env_bool("LOG_JSON", False))

    # =========================================================================
    # TIMING & DELAYS
    # =========================================================================
    BUFFER_DELAY: float = field(default_factory=lambda: float(_env("BUFFER_DELAY", "3.5")))
    TEST_MODE: bool = field(default_factory=lambda: _env_bool("LUNA_TEST_MODE", False))

    # Job intervals (seconds)
    JOB_PROACTIVE_INTERVAL: int = field(default_factory=lambda: _env_int("JOB_PROACTIVE_INTERVAL", 1800))
    JOB_WINBACK_INTERVAL: int = field(default_factory=lambda: _env_int("JOB_WINBACK_INTERVAL", 7200))
    JOB_CHURN_INTERVAL: int = field(default_factory=lambda: _env_int("JOB_CHURN_INTERVAL", 3600))
    JOB_COMPRESSION_INTERVAL: int = field(default_factory=lambda: _env_int("JOB_COMPRESSION_INTERVAL", 86400))

    # =========================================================================
    # TIMEZONE
    # =========================================================================
    TIMEZONE: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Paris"))

    @property
    def PARIS_TZ(self) -> ZoneInfo:
        """Alias for TIMEZONE."""
        return self.TIMEZONE

    # =========================================================================
    # RATE LIMITS
    # =========================================================================
    RATE_LIMIT_MESSAGES: int = field(default_factory=lambda: _env_int("RATE_LIMIT_MESSAGES", 30))
    RATE_LIMIT_WINDOW: int = field(default_factory=lambda: _env_int("RATE_LIMIT_WINDOW", 60))

    # =========================================================================
    # THRESHOLDS (Phase system)
    # =========================================================================
    PHASE_THRESHOLDS: dict = field(default_factory=lambda: {
        "HOOK": 0,        # Messages 0-50
        "CONNECT": 50,    # Messages 50-150
        "ATTACH": 150,    # Messages 150-400
        "TENSION": 400,   # Messages 400-600
        "PAYWALL": 600,   # Message 600 = paywall
        "LIBRE": 601,     # After paywall
    })

    # NSFW thresholds (momentum-based)
    NSFW_TIER_THRESHOLDS: dict = field(default_factory=lambda: {
        "SFW": 0,         # Tier 1: Haiku
        "FLIRT": 30,      # Tier 2: Magnum suggestive
        "NSFW": 60,       # Tier 3: Magnum explicit
    })

    # =========================================================================
    # PROACTIVE MESSAGES
    # =========================================================================
    MAX_PROACTIVE_PER_DAY: int = 2
    PROACTIVE_MIN_HOURS: int = 4  # Min hours since last message

    # =========================================================================
    # VERSION
    # =========================================================================
    BOT_VERSION: str = "7.0.0"


# Singleton instance
settings = Settings()


# =============================================================================
# NSFW KEYWORDS (moved from luna_simple.py)
# =============================================================================

NSFW_KEYWORDS = [
    "nude", "nue", "nu", "sein", "chatte", "bite", "sucer", "lecher", "baiser",
    "jouir", "orgasme", "excitée", "bandé", "mouillée", "gémis", "déshabille",
    "lingerie", "string", "culotte", "touche-toi", "branle", "masturbe", "sexe",
    "à poil", "toute nue", "photo hot", "photo sexy", "montre-moi", "je te veux",
    "j'ai envie de toi", "baise-moi", "suce", "queue", "téton"
]

CLIMAX_PATTERNS = [
    "j'ai joui", "je jouis", "je viens de jouir",
    "je tremble encore", "je tremble de partout",
    "c'était incroyable", "putain c'était bon",
]


# =============================================================================
# VALIDATION
# =============================================================================

def validate_settings() -> list[str]:
    """
    Validate required settings.

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not settings.TELEGRAM_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")

    if not settings.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is required")

    if not settings.OPENROUTER_API_KEY:
        errors.append("OPENROUTER_API_KEY is required")

    return errors
