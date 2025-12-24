"""Rate limiting for Luna Bot."""
import time
from collections import defaultdict


class RateLimiter:
    """Rate limiter avec sliding window."""

    def __init__(self, window_seconds: float = 60.0, max_requests: int = 20):
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._requests: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Verifie si l'utilisateur peut envoyer un message."""
        now = time.time()

        # Nettoyer les anciennes requetes
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < self.window_seconds
        ]

        # Verifier la limite
        if len(self._requests[user_id]) >= self.max_requests:
            return False

        # Enregistrer la requete
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
