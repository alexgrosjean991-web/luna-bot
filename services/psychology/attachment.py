"""
Attachment Score Tracker
------------------------
Mesure et suit le niveau d'attachement du user pour optimiser timing paywall.

Impact: Meilleur timing = +2-3% conversion
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AttachmentMetrics:
    """Métriques d'attachement."""
    score: float                    # 0-100
    engagement_rate: float          # Messages user / messages Luna
    avg_response_time: float        # Secondes
    session_count: int
    total_messages: int
    user_initiated_ratio: float     # % conversations initiées par user
    emotional_depth: float          # 0-1, basé sur contenu
    inside_jokes_count: int
    vulnerabilities_shared: int     # Fois où user s'est confié


class AttachmentTracker:
    """
    Suit et calcule le score d'attachement.

    Utilisé pour:
    - Optimiser timing du paywall
    - Ajuster intensité des techniques
    - Prédire conversion
    """

    # Seuils pour paywall
    PAYWALL_READY_SCORE = 65
    OPTIMAL_PAYWALL_SCORE = 80

    # Indicateurs de profondeur émotionnelle
    DEEP_INDICATORS = [
        "je me sens", "j'ai peur", "ça me fait", "en vrai",
        "j'avoue", "entre nous", "j'ai jamais dit", "tu comprends",
        "ça me touche", "tu me manques", "j'aime bien", "je t'aime",
        "j'ai confiance", "je suis triste", "je suis content",
        "ça m'énerve", "je suis stressé", "j'ai besoin"
    ]

    def calculate_score(self, data: dict) -> AttachmentMetrics:
        """
        Calcule le score d'attachement complet.

        Args:
            data: Données brutes (messages, timestamps, etc)

        Returns:
            AttachmentMetrics avec score calculé
        """
        # Extraire métriques de base
        engagement_rate = self._calc_engagement_rate(data)
        avg_response_time = self._calc_avg_response_time(data)
        user_initiated_ratio = self._calc_user_initiated(data)
        emotional_depth = self._calc_emotional_depth(data)

        sessions = data.get("session_count", 1)
        jokes = data.get("inside_jokes_count", 0)
        vulns = data.get("vulnerabilities_shared", 0)
        total_messages = data.get("total_messages", 0)

        # Calculer score composite (0-100)
        score = 0

        # Engagement (0-15 points)
        score += min(engagement_rate * 20, 15)

        # Response time (0-10 points)
        if avg_response_time < 120:  # <2min
            score += 10
        elif avg_response_time < 300:  # <5min
            score += 7
        elif avg_response_time < 600:  # <10min
            score += 4
        else:
            score += 2

        # Sessions (0-15 points)
        score += min(sessions * 3, 15)

        # User initiated (0-15 points)
        score += user_initiated_ratio * 15

        # Emotional depth (0-20 points)
        score += emotional_depth * 20

        # Inside jokes (0-10 points)
        score += min(jokes * 3, 10)

        # Vulnerabilities (0-15 points)
        score += min(vulns * 5, 15)

        # Total messages bonus (max 5 points)
        score += min(total_messages / 20, 5)

        final_score = min(score, 100)

        logger.debug(
            f"Attachment score: {final_score:.1f} "
            f"(engagement={engagement_rate:.2f}, depth={emotional_depth:.2f}, "
            f"sessions={sessions}, jokes={jokes})"
        )

        return AttachmentMetrics(
            score=final_score,
            engagement_rate=engagement_rate,
            avg_response_time=avg_response_time,
            session_count=sessions,
            total_messages=total_messages,
            user_initiated_ratio=user_initiated_ratio,
            emotional_depth=emotional_depth,
            inside_jokes_count=jokes,
            vulnerabilities_shared=vulns
        )

    def is_paywall_ready(self, metrics: AttachmentMetrics) -> bool:
        """Détermine si l'utilisateur est prêt pour le paywall."""
        return metrics.score >= self.PAYWALL_READY_SCORE

    def is_optimal_paywall_timing(self, metrics: AttachmentMetrics) -> bool:
        """Détermine si c'est le moment optimal pour le paywall."""
        return metrics.score >= self.OPTIMAL_PAYWALL_SCORE

    def get_conversion_probability(self, metrics: AttachmentMetrics) -> float:
        """
        Estime la probabilité de conversion.

        Args:
            metrics: Métriques d'attachement

        Returns:
            Probabilité 0-1
        """
        # Base: score contribue 50% max
        base_prob = metrics.score / 100 * 0.5

        # Bonus facteurs clés
        if metrics.emotional_depth > 0.7:
            base_prob += 0.10

        if metrics.inside_jokes_count >= 2:
            base_prob += 0.05

        if metrics.vulnerabilities_shared >= 2:
            base_prob += 0.10

        if metrics.user_initiated_ratio > 0.4:
            base_prob += 0.05

        if metrics.session_count >= 5:
            base_prob += 0.05

        return min(base_prob, 0.80)

    def get_paywall_recommendation(self, metrics: AttachmentMetrics, day_count: int) -> dict:
        """
        Retourne une recommandation pour le paywall.

        Args:
            metrics: Métriques d'attachement
            day_count: Jour de la relation

        Returns:
            Dict avec recommandation
        """
        conversion_prob = self.get_conversion_probability(metrics)

        if day_count < 5:
            return {
                "should_paywall": False,
                "reason": "Trop tôt (jour < 5)",
                "score": metrics.score,
                "conversion_prob": conversion_prob
            }

        if metrics.score < self.PAYWALL_READY_SCORE:
            return {
                "should_paywall": False,
                "reason": f"Score insuffisant ({metrics.score:.0f} < {self.PAYWALL_READY_SCORE})",
                "score": metrics.score,
                "conversion_prob": conversion_prob
            }

        is_optimal = metrics.score >= self.OPTIMAL_PAYWALL_SCORE

        return {
            "should_paywall": True,
            "is_optimal": is_optimal,
            "reason": "Optimal" if is_optimal else "Prêt mais pas optimal",
            "score": metrics.score,
            "conversion_prob": conversion_prob
        }

    def _calc_engagement_rate(self, data: dict) -> float:
        """Calcule le taux d'engagement."""
        user_msgs = data.get("user_messages", 0)
        luna_msgs = data.get("luna_messages", 0)

        if luna_msgs == 0:
            return 0

        # Ratio normalisé (1.0 = équilibré, >1 = user très engagé)
        ratio = user_msgs / luna_msgs
        return min(ratio, 1.5) / 1.5

    def _calc_avg_response_time(self, data: dict) -> float:
        """Calcule le temps de réponse moyen."""
        response_times = data.get("response_times", [])

        if not response_times:
            return 600  # Default 10min

        return sum(response_times) / len(response_times)

    def _calc_user_initiated(self, data: dict) -> float:
        """Calcule le ratio de conversations initiées par user."""
        user_initiated = data.get("user_initiated_count", 0)
        total_sessions = max(data.get("session_count", 1), 1)

        return min(user_initiated / total_sessions, 1.0)

    def _calc_emotional_depth(self, data: dict) -> float:
        """Calcule la profondeur émotionnelle des échanges."""
        messages = data.get("user_messages_content", [])

        if not messages:
            return 0

        deep_count = 0
        for msg in messages:
            msg_lower = msg.lower()
            if any(ind in msg_lower for ind in self.DEEP_INDICATORS):
                deep_count += 1

        # Normaliser: ~20% de messages profonds = score max
        ratio = deep_count / len(messages)
        return min(ratio * 5, 1.0)

    def count_vulnerability_shares(self, messages: list[str]) -> int:
        """Compte le nombre de partages de vulnérabilité."""
        vulnerability_patterns = [
            "j'ai jamais dit", "entre nous", "j'ai peur",
            "je suis triste", "ça me fait mal", "j'avoue",
            "j'ai honte", "je me sens seul", "personne sait"
        ]

        count = 0
        for msg in messages:
            msg_lower = msg.lower()
            if any(p in msg_lower for p in vulnerability_patterns):
                count += 1

        return count
