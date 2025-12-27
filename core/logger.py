"""
Centralized logging for Luna Bot.

Usage:
    from core import get_logger
    logger = get_logger(__name__)
    logger.info("Message")
"""

import logging
import os
import sys
from typing import Optional


# Global log level (set from env)
_LOG_LEVEL: int = logging.INFO
_INITIALIZED: bool = False


class LunaFormatter(logging.Formatter):
    """Compact formatter for production logs."""

    FORMATS = {
        logging.DEBUG: "\033[90m%(asctime)s [DBG] %(name)s: %(message)s\033[0m",
        logging.INFO: "%(asctime)s [INF] %(name)s: %(message)s",
        logging.WARNING: "\033[33m%(asctime)s [WRN] %(name)s: %(message)s\033[0m",
        logging.ERROR: "\033[31m%(asctime)s [ERR] %(name)s: %(message)s\033[0m",
        logging.CRITICAL: "\033[31;1m%(asctime)s [CRT] %(name)s: %(message)s\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for production (structured logs)."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime

        log_obj = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(level: Optional[str] = None, json_format: bool = False) -> None:
    """
    Configure logging for the entire application.

    Args:
        level: "DEBUG", "INFO", "WARNING", "ERROR" (default from LOG_LEVEL env)
        json_format: Use JSON format for production
    """
    global _LOG_LEVEL, _INITIALIZED

    if _INITIALIZED:
        return

    # Get level from env or argument
    level_str = level or os.getenv("LOG_LEVEL", "INFO")
    _LOG_LEVEL = getattr(logging, level_str.upper(), logging.INFO)

    # Root logger config
    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add our handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(_LOG_LEVEL)

    if json_format or os.getenv("LOG_JSON", "").lower() == "true":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(LunaFormatter())

    root.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.

    Args:
        name: Usually __name__

    Returns:
        Configured logger
    """
    if not _INITIALIZED:
        setup_logging()
    return logging.getLogger(name)
