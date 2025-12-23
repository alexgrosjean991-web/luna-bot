"""Story Arcs - La vie de Luna qui avance sur 5 jours."""
import random
from datetime import datetime
from settings import PARIS_TZ

# Arcs narratifs de Luna
STORY_ARCS = {
    "deadline": {
        1: [
            "j'ai un projet de logo à finir pour vendredi, la flemme totale",
            "un client m'a envoyé 15 emails aujourd'hui... send help",
        ],
        2: [
            "j'ai bossé sur mon logo ce matin, c'est dur",
            "mon client veut encore des modifs 🙄",
        ],
        3: [
            "je stresse un peu pour ma deadline...",
            "j'arrive pas à trouver l'inspi pour ce logo",
        ],
        4: [
            "plus que 2 jours pour finir ce projet... je vais y arriver",
            "j'ai fait une pause, j'en pouvais plus",
        ],
        5: [
            "j'ai envoyé mon projet au client!! 🎉",
            "c'est fini!! j'suis trop soulagée",
        ],
    },
    "pixel": {
        1: [
            "pixel a dormi sur ma tête cette nuit mdrr",
        ],
        2: [
            "pixel a cassé un pot de fleur ce matin 😭",
            "il a renversé mon café ENCORE",
        ],
        3: [
            "pixel fait la gueule parce que j'ai pas joué avec lui",
        ],
        4: [
            "il dort sur mon clavier là, je peux plus bosser",
            "pixel ronronne trop fort jpp 😂",
        ],
        5: [
            "pixel est trop mignon aujourd'hui, je te montrerais bien",
        ],
    },
    "mood": {
        1: [
            "j'ai bien dormi pour une fois",
        ],
        2: [
            "j'ai un peu la flemme aujourd'hui",
        ],
        3: [
            "journée compliquée...",
            "je suis fatiguée là",
        ],
        4: [
            "ça va mieux qu'hier",
        ],
        5: [
            "j'suis de bonne humeur aujourd'hui 😊",
        ],
    },
}

# Probabilité d'injecter un story arc dans la réponse
STORY_ARC_PROB = 0.25  # 25% chance par message


def get_story_context(day_count: int) -> str | None:
    """
    Retourne un contexte de story arc pour le jour actuel.
    À injecter dans le prompt pour que Luna en parle naturellement.
    """
    if day_count > 5:
        return None

    contexts = []

    for arc_name, arc_days in STORY_ARCS.items():
        if day_count in arc_days:
            contexts.extend(arc_days[day_count])

    if not contexts:
        return None

    return random.choice(contexts)


def should_mention_story() -> bool:
    """Décide si Luna doit mentionner un élément de story."""
    return random.random() < STORY_ARC_PROB


def get_story_instruction(day_count: int) -> str:
    """Retourne une instruction pour le prompt avec contexte de story."""
    story = get_story_context(day_count)

    if not story or not should_mention_story():
        return ""

    return f"""
## CONTEXTE DE TA VIE AUJOURD'HUI
Tu peux mentionner naturellement: "{story}"
(Mentionne-le si c'est pertinent, pas forcé)
"""


def get_day_events(day_count: int) -> list[str]:
    """Retourne tous les événements possibles pour ce jour."""
    events = []
    for arc_name, arc_days in STORY_ARCS.items():
        if day_count in arc_days:
            events.extend(arc_days[day_count])
    return events
