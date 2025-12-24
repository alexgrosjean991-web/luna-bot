"""Rate limiting for Luna Bot.

Implements sliding window rate limiting per user to prevent abuse.
Thread-safe for asyncio single-threaded execution.
"""
import time
from collections import defaultdict


class RateLimiter:
    """
    Sliding window rate limiter.

    Tracks request timestamps per user and enforces max_requests
    within window_seconds. Atomic cleanup-and-check prevents
    race conditions in asyncio single-threaded context.

    Attributes:
        window_seconds: Time window in seconds for rate limiting
        max_requests: Maximum allowed requests per window
    """

    def __init__(self, window_seconds: float = 60.0, max_requests: int = 20) -> None:
        """Initialize rate limiter with configurable limits."""
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._requests: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """
        Check if user can send a message.

        Performs atomic cleanup and check:
        1. Remove expired timestamps outside window
        2. Check if under limit
        3. Record new request if allowed

        Args:
            user_id: Telegram user ID

        Returns:
            True if request allowed, False if rate limited
        """
        now = time.time()

        # Atomic: cleanup + check + record in one operation
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < self.window_seconds
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            return False

        self._requests[user_id].append(now)
        return True

    def get_wait_time(self, user_id: int) -> float:
        """Retourne le temps d'attente avant de pouvoir renvoyer."""
        if not self._requests[user_id]:
            return 0
        oldest = min(self._requests[user_id])
        return max(0, self.window_seconds - (time.time() - oldest))


# Global singleton: 20 messages par minute max
rate_limiter = RateLimiter(window_seconds=60.0, max_requests=20)
