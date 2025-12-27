"""
NSFW Gate - Garde-fous minimalistes
3 compteurs seulement. Luna gère le reste.
"""

from datetime import datetime, date
from typing import Tuple, Optional


class NSFWGate:
    """
    Gates NSFW minimalistes.
    3 compteurs - Luna gère tout le reste via prompt.
    """

    def __init__(self):
        self.last_nsfw_at: Optional[datetime] = None
        self.messages_since_nsfw: int = 0
        self.nsfw_count_today: int = 0
        self.nsfw_date: Optional[date] = None

    def check(self) -> Tuple[bool, Optional[str]]:
        """
        Vérifie si NSFW possible.
        Returns: (True, None) si OK, (False, reason) si bloqué.
        """

        # Reset journalier
        if self.nsfw_date != date.today():
            self.nsfw_count_today = 0
            self.nsfw_date = date.today()

        # Gate 1: Max 2/jour
        if self.nsfw_count_today >= 2:
            return False, "daily_limit"

        # Gate 2: Cooldown 8h
        if self.last_nsfw_at:
            hours = (datetime.now() - self.last_nsfw_at).total_seconds() / 3600
            if hours < 8:
                return False, "cooldown"

        # Gate 3: 20 messages minimum
        if self.messages_since_nsfw < 20:
            return False, "not_enough_messages"

        return True, None

    def on_message(self):
        """Appelé à chaque message user."""
        self.messages_since_nsfw += 1

    def on_nsfw_done(self):
        """Appelé quand session NSFW terminée (climax détecté)."""
        self.last_nsfw_at = datetime.now()
        self.messages_since_nsfw = 0
        self.nsfw_count_today += 1
        self.nsfw_date = date.today()

    def to_dict(self) -> dict:
        """Pour sauvegarder en DB/JSON."""
        return {
            "last_nsfw_at": self.last_nsfw_at.isoformat() if self.last_nsfw_at else None,
            "messages_since_nsfw": self.messages_since_nsfw,
            "nsfw_count_today": self.nsfw_count_today,
            "nsfw_date": self.nsfw_date.isoformat() if self.nsfw_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NSFWGate":
        """Pour charger depuis DB/JSON."""
        gate = cls()
        if data.get("last_nsfw_at"):
            gate.last_nsfw_at = datetime.fromisoformat(data["last_nsfw_at"])
        gate.messages_since_nsfw = data.get("messages_since_nsfw", 0)
        gate.nsfw_count_today = data.get("nsfw_count_today", 0)
        if data.get("nsfw_date"):
            gate.nsfw_date = date.fromisoformat(data["nsfw_date"])
        return gate
