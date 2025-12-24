"""
User Timing Learner
-------------------
Apprend les patterns temporels de chaque utilisateur.

Tracks:
- Heures d'activite preferees
- Jours les plus actifs
- Temps de reponse moyen
- Sessions typiques (duree, frequence)

Usage:
- Optimiser timing des messages proactifs
- Predire quand l'user sera disponible
- Adapter le comportement de Luna selon l'heure
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class HourlyActivity:
    """Activite par heure."""
    hour: int
    message_count: int
    avg_response_time_seconds: float
    engagement_score: float  # Longueur msg * reactivite


@dataclass
class UserTimingProfile:
    """Profil temporel d'un utilisateur."""
    user_id: int
    peak_hours: list[int]  # Top 3 heures d'activite
    active_days: list[int]  # Jours les plus actifs (0=lundi)
    avg_response_time_seconds: float
    avg_session_duration_minutes: float
    typical_session_messages: int
    last_updated: datetime = field(default_factory=datetime.now)

    def is_good_time(self, hour: int, day: int) -> bool:
        """Verifie si c'est un bon moment pour contacter."""
        hour_ok = hour in self.peak_hours or (self.peak_hours and abs(hour - self.peak_hours[0]) <= 2)
        day_ok = day in self.active_days or len(self.active_days) == 0
        return hour_ok and day_ok

    def get_best_hour(self) -> int:
        """Retourne la meilleure heure pour contacter."""
        if self.peak_hours:
            return self.peak_hours[0]
        return 20  # Default: 20h


class UserTimingLearner:
    """Apprend les patterns temporels des utilisateurs."""

    def __init__(self):
        self.profiles: dict[int, UserTimingProfile] = {}
        self.activity_cache: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    def record_activity(
        self,
        user_id: int,
        timestamp: datetime,
        message_length: int,
        is_response: bool = False,
        response_time_seconds: float = None
    ) -> None:
        """
        Enregistre une activite utilisateur.

        Args:
            user_id: ID utilisateur
            timestamp: Moment de l'activite
            message_length: Longueur du message
            is_response: Si c'est une reponse a Luna
            response_time_seconds: Temps de reponse si applicable
        """
        hour = timestamp.hour
        day = timestamp.weekday()

        # Incrementer le compteur d'activite par heure
        self.activity_cache[user_id][hour] += 1

        logger.debug(f"Activity recorded: user={user_id}, hour={hour}, day={day}")

    def calculate_profile(
        self,
        user_id: int,
        message_history: list[dict],
        session_data: dict
    ) -> UserTimingProfile:
        """
        Calcule le profil temporel depuis l'historique.

        Args:
            user_id: ID utilisateur
            message_history: Historique des messages avec timestamps
            session_data: Donnees de session (count, avg_duration, etc.)

        Returns:
            UserTimingProfile
        """
        # Compter les messages par heure
        hour_counts = defaultdict(int)
        day_counts = defaultdict(int)
        response_times = []

        prev_timestamp = None
        for msg in message_history:
            if msg.get("role") != "user":
                continue

            timestamp = msg.get("created_at")
            if timestamp:
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except ValueError:
                        continue

                hour_counts[timestamp.hour] += 1
                day_counts[timestamp.weekday()] += 1

                # Calculer temps de reponse
                if prev_timestamp:
                    delta = (timestamp - prev_timestamp).total_seconds()
                    if 0 < delta < 3600:  # Max 1h pour etre considere comme reponse
                        response_times.append(delta)

                prev_timestamp = timestamp

        # Top 3 heures
        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, _ in sorted_hours[:3]]

        # Jours actifs (plus de 20% de l'activite totale)
        total_msgs = sum(day_counts.values()) or 1
        active_days = [d for d, c in day_counts.items() if c / total_msgs > 0.15]

        # Moyenne temps de reponse
        avg_response = sum(response_times) / len(response_times) if response_times else 300

        profile = UserTimingProfile(
            user_id=user_id,
            peak_hours=peak_hours if peak_hours else [20, 21, 22],
            active_days=active_days if active_days else list(range(7)),
            avg_response_time_seconds=avg_response,
            avg_session_duration_minutes=session_data.get("avg_duration", 15),
            typical_session_messages=session_data.get("avg_messages", 10),
        )

        self.profiles[user_id] = profile
        return profile

    def get_profile(self, user_id: int) -> Optional[UserTimingProfile]:
        """Recupere le profil d'un utilisateur."""
        return self.profiles.get(user_id)

    def get_optimal_send_time(
        self,
        user_id: int,
        current_hour: int,
        current_day: int
    ) -> tuple[int, int]:
        """
        Calcule le meilleur moment pour envoyer un message.

        Args:
            user_id: ID utilisateur
            current_hour: Heure actuelle
            current_day: Jour actuel

        Returns:
            (hour, minutes_to_wait)
        """
        profile = self.profiles.get(user_id)

        if not profile or not profile.peak_hours:
            # Default: prochain creneau soir
            if current_hour < 20:
                return (20, (20 - current_hour) * 60)
            elif current_hour < 22:
                return (current_hour, 0)  # Maintenant
            else:
                return (20, (24 - current_hour + 20) * 60)

        # Trouver la prochaine peak hour
        best_hour = profile.peak_hours[0]

        for peak in profile.peak_hours:
            if peak > current_hour:
                best_hour = peak
                break

        if best_hour <= current_hour:
            # Demain
            minutes_to_wait = (24 - current_hour + best_hour) * 60
        else:
            minutes_to_wait = (best_hour - current_hour) * 60

        return (best_hour, minutes_to_wait)

    def should_send_now(
        self,
        user_id: int,
        current_hour: int,
        current_day: int,
        urgency: str = "normal"
    ) -> bool:
        """
        Determine si c'est le bon moment pour envoyer.

        Args:
            user_id: ID utilisateur
            current_hour: Heure actuelle
            current_day: Jour actuel
            urgency: "low", "normal", "high"

        Returns:
            True si bon moment
        """
        # Urgence haute = toujours envoyer (sauf nuit)
        if urgency == "high":
            return 8 <= current_hour <= 23

        profile = self.profiles.get(user_id)

        if not profile:
            # Default: soir seulement
            return 18 <= current_hour <= 22

        # Verifier si c'est une peak hour (+/- 1h)
        for peak in profile.peak_hours:
            if abs(current_hour - peak) <= 1:
                return True

        # Urgence normale: accepter +/- 2h des peaks
        if urgency == "normal":
            for peak in profile.peak_hours:
                if abs(current_hour - peak) <= 2:
                    return True

        return False


# Singleton
user_timing = UserTimingLearner()
