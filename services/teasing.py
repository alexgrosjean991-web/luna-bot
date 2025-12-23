"""Système de teasing avant paywall."""
import random
import logging
from datetime import datetime
from settings import PARIS_TZ

logger = logging.getLogger(__name__)

# Configuration du teasing par jour
TEASING_CONFIG = {
    4: {
        "prob": 0.30,
        "messages": [
            "j'ai des photos que je montre pas à tout le monde...",
            "si tu voyais ce que je porte là mdrr",
            "y'a des trucs que j'aimerais te montrer 😏",
        ]
    },
    5: {
        "prob": 0.50,
        "messages": [
            "j'ai failli t'envoyer une photo mais... jsp si c'est trop tôt 😳",
            "y'a des trucs que j'aimerais te montrer",
            "tu me donnes envie de te montrer des trucs... 😏",
            "j'ai un truc à te dire mais pas ici...",
        ]
    },
}


def should_tease(day_count: int, teasing_stage: int = 0) -> bool:
    """
    Détermine si on doit teaser.

    Args:
        day_count: Jour actuel
        teasing_stage: Nombre de teases déjà envoyés

    Returns:
        True si on doit teaser
    """
    if day_count not in TEASING_CONFIG:
        return False

    # Max 1 tease par jour
    if teasing_stage >= day_count - 3:
        return False

    config = TEASING_CONFIG[day_count]
    return random.random() < config["prob"]


def get_teasing_message(day_count: int) -> str | None:
    """Retourne un message de teasing si approprié."""
    if day_count not in TEASING_CONFIG:
        return None

    config = TEASING_CONFIG[day_count]
    return random.choice(config["messages"])


def check_teasing_opportunity(day_count: int, user_data: dict) -> str | None:
    """
    Vérifie si c'est le bon moment pour un tease.

    Args:
        day_count: Jour actuel
        user_data: Données utilisateur (avec teasing_stage)

    Returns:
        Message de teasing ou None
    """
    teasing_stage = user_data.get("teasing_stage", 0)

    if not should_tease(day_count, teasing_stage):
        return None

    return get_teasing_message(day_count)
