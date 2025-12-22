import os
from dataclasses import dataclass

@dataclass
class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Database
    DB_HOST: str = os.getenv("DB_HOST", "postgres")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "luna")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "luna_password")
    DB_NAME: str = os.getenv("DB_NAME", "luna_db")
    
    # LLM APIs
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free")
    
    # Trial settings
    TRIAL_DAYS: int = 5
    FREE_MESSAGES_PER_DAY: int = 9999  # Set to low number in production
    
    # Pricing (EUR)
    CHOUCHOU_WEEKLY_PRICE: float = 25.0


config = Config()
