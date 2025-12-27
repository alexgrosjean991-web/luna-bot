"""
Core infrastructure for Luna Bot.

- logger: Centralized logging with DEBUG/INFO switch
- errors: Custom exceptions + graceful degradation
- database: Connection pooling + retry helpers
"""

from core.logger import get_logger, setup_logging
from core.errors import LunaError, LLMError, DatabaseError, safe_execute
from core.database import Database, get_db

__all__ = [
    "get_logger",
    "setup_logging",
    "LunaError",
    "LLMError",
    "DatabaseError",
    "safe_execute",
    "Database",
    "get_db",
]
