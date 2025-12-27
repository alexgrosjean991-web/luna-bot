"""
Error handling and graceful degradation for Luna Bot.

Usage:
    from core import safe_execute, LLMError

    result = await safe_execute(risky_function(), fallback="default")
"""

import asyncio
import functools
from typing import Any, Callable, Optional, TypeVar

from core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class LunaError(Exception):
    """Base exception for Luna Bot."""
    pass


class LLMError(LunaError):
    """Error from LLM API (OpenRouter, Anthropic)."""

    def __init__(self, message: str, provider: str = "unknown", status_code: int = 0):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class DatabaseError(LunaError):
    """Database operation failed."""

    def __init__(self, message: str, operation: str = "unknown"):
        super().__init__(message)
        self.operation = operation


class RateLimitError(LunaError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class PaywallError(LunaError):
    """User needs to pay."""
    pass


# =============================================================================
# GRACEFUL DEGRADATION
# =============================================================================

async def safe_execute(
    coro,
    fallback: T = None,
    error_message: str = "Operation failed",
    log_error: bool = True,
) -> T:
    """
    Execute coroutine with graceful degradation.

    Args:
        coro: Async function to execute
        fallback: Value to return on error
        error_message: Message to log on error
        log_error: Whether to log the error

    Returns:
        Result or fallback value
    """
    try:
        return await coro
    except Exception as e:
        if log_error:
            logger.error(f"{error_message}: {e}", exc_info=True)
        return fallback


def with_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for retry with exponential backoff.

    Args:
        max_attempts: Max retry attempts
        delay: Initial delay between retries
        backoff: Multiply delay by this after each retry
        exceptions: Tuple of exceptions to catch
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")

            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# NATURAL ERROR MESSAGES (for Luna to say)
# =============================================================================

NATURAL_ERROR_MESSAGES = [
    "hm attends j'ai bugué 2 sec",
    "oups j'ai perdu le fil, tu disais ?",
    "ah merde j'ai freeze, redis-moi ?",
    "ptdr j'ai eu un blanc, c'était quoi ?",
    "déso mon tel a lagué",
]


def get_natural_error() -> str:
    """Get a random natural error message for Luna."""
    import random
    return random.choice(NATURAL_ERROR_MESSAGES)
