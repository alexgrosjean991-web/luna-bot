"""
LLM Router - Sélectionne le modèle optimal selon le parcours utilisateur.

Routes:
    - J1-J4: Haiku (construction engagement)
    - J5 20h+ avec teasing >= 5: Venice (aperçu premium)
    - J6+ abonné: Venice (premium complet)
"""

from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_llm_config(
    day_count: int,
    teasing_stage: int,
    subscription_status: str,
    hour: int | None = None
) -> tuple[str, str]:
    """
    Retourne (provider, model) selon contexte utilisateur.

    Args:
        day_count: Jour de la relation (1-N)
        teasing_stage: Niveau d'engagement (0-8)
        subscription_status: "trial" ou "active"
        hour: Heure actuelle (optionnel, pour tests)

    Returns:
        Tuple (provider, model_name)

    Logic:
        - Abonné actif → OpenRouter/Euryale
        - J5 20h+ avec teasing >= 5 → OpenRouter (aperçu)
        - J5 teasing >= 6 (user très engagé) → OpenRouter
        - Sinon → Anthropic/Haiku
    """
    if hour is None:
        hour = datetime.now().hour

    # Abonnés = toujours premium
    if subscription_status == "active":
        logger.info(f"Router: Venice (abonné actif)")
        return ("venice", "venice-uncensored")

    # J5 soir + engagement élevé = aperçu premium
    if day_count == 5:
        if hour >= 20 and teasing_stage >= 5:
            logger.info(f"Router: Venice (J5 soir, teasing={teasing_stage})")
            return ("venice", "venice-uncensored")
        if teasing_stage >= 6:
            logger.info(f"Router: Venice (J5, high teasing={teasing_stage})")
            return ("venice", "venice-uncensored")

    # J6+ non abonné mais très engagé = aperçu limité
    if day_count >= 6 and teasing_stage >= 7:
        logger.info(f"Router: Venice (J{day_count}, very high teasing)")
        return ("venice", "venice-uncensored")

    # Default: Haiku
    logger.info(f"Router: Haiku (J{day_count}, teasing={teasing_stage})")
    return ("anthropic", "claude-3-5-haiku-20241022")


def detect_engagement_signal(message: str) -> int:
    """
    Détecte les signaux d'engagement dans le message utilisateur.

    Args:
        message: Message de l'utilisateur

    Returns:
        0 (neutre), 1 (intérêt), 2 (fort intérêt)
    """
    msg = message.lower()

    # Signaux d'intérêt très fort (+2)
    fort = [
        "envie de toi", "te veux", "besoin de toi", "tellement envie",
        "je te veux", "j'ai envie de toi", "tu me rends fou",
        "tu me manques trop", "j'arrête pas de penser à toi"
    ]
    if any(s in msg for s in fort):
        return 2

    # Signaux d'intérêt moyen (+1)
    moyen = [
        "envie", "manque", "pense à toi", "t'adore", "belle", "canon",
        "sexy", "mignon", "craquante", "magnifique", "parfaite",
        "j'aime", "tu me plais", "attiré", "chaud"
    ]
    if any(s in msg for s in moyen):
        return 1

    return 0


def is_premium_session(provider: str) -> bool:
    """Vérifie si on est en session premium (Venice)."""
    return provider == "venice"
