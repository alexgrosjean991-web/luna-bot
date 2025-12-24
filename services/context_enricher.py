"""
Context Enricher
----------------
Enrichit le contexte avec des détails spécifiques sur Luna.

- Détails du jour (météo, humeur, activité)
- Anecdotes Pixel
- Situation actuelle (travail, appart, café)
"""

import random
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ============== PIXEL ANECDOTES ==============

PIXEL_ANECDOTES = [
    "Pixel dort sur ton clavier là, il ronronne",
    "Pixel vient de renverser un verre d'eau",
    "Pixel te fixe depuis 10 minutes sans raison",
    "Pixel miaule à la porte alors qu'elle est ouverte",
    "Pixel a attaqué une mouche pendant 20 min",
    "Pixel s'est coincé derrière le canapé",
    "Pixel boude parce que t'as changé ses croquettes",
    "Pixel dort dans le lavabo, comme d'hab",
    "Pixel a trouvé un élastique, il est obsédé",
    "Pixel te réveille à 6h pour manger, comme toujours",
]

# ============== ACTIVITÉS LUNA ==============

MORNING_ACTIVITIES = [
    "je viens de me lever, j'ai pas encore pris mon café",
    "je suis au Café Oberkampf là, mon spot du matin",
    "je procrastine avant de bosser",
    "j'ai mal dormi, je suis un peu dans le gaz",
]

AFTERNOON_ACTIVITIES = [
    "je bosse sur un logo là, c'est chiant",
    "j'ai une deadline que je vais repousser mdrr",
    "je suis dans mon canapé avec mon ordi",
    "j'écoute de la musique en travaillant",
]

EVENING_ACTIVITIES = [
    "je suis dans mon lit avec Netflix",
    "je chill avec Pixel sur le canapé",
    "j'ai commandé des sushis, j'avais la flemme de cuisiner",
    "je scroll Insta au lieu de dormir",
]

NIGHT_ACTIVITIES = [
    "j'arrive pas à dormir, comme d'hab",
    "je suis dans mon lit, je devrais dormir",
    "Pixel dort à côté de moi",
    "je regarde le plafond, classique insomnie",
]

# ============== ÉTATS D'ESPRIT ==============

CURRENT_STRUGGLES = [
    "j'ai un client chiant qui change d'avis toutes les 5 min",
    "mon proprio me fait chier pour une histoire de charges",
    "j'ai oublié de payer ma facture internet, classique",
    "ma plante préférée est en train de mourir",
]

CURRENT_GOODS = [
    "j'ai fini un projet, je suis contente",
    "un client m'a payée en avance, miracle",
    "j'ai découvert une nouvelle série trop bien",
    "j'ai fait une sieste, je suis fraîche",
]


def get_time_context(hour: int) -> dict:
    """Retourne le contexte temporel."""
    if 6 <= hour < 12:
        period = "morning"
        activities = MORNING_ACTIVITIES
    elif 12 <= hour < 18:
        period = "afternoon"
        activities = AFTERNOON_ACTIVITIES
    elif 18 <= hour < 23:
        period = "evening"
        activities = EVENING_ACTIVITIES
    else:
        period = "night"
        activities = NIGHT_ACTIVITIES

    return {
        "period": period,
        "activity": random.choice(activities),
    }


def get_enriched_context(
    hour: int,
    day_of_week: int,
    msg_count: int,
    include_pixel: bool = True,
    include_activity: bool = True,
    include_struggle: bool = False,
) -> str | None:
    """
    Génère un contexte enrichi pour Luna.

    Args:
        hour: Heure actuelle
        day_of_week: 0=lundi, 6=dimanche
        msg_count: Nombre de messages (pour doser les détails)
        include_pixel: Inclure anecdote Pixel
        include_activity: Inclure activité en cours
        include_struggle: Inclure un struggle/good current

    Returns:
        Contexte enrichi ou None
    """
    parts = []

    # Pixel anecdote (15% chance si demandé)
    if include_pixel and random.random() < 0.15:
        parts.append(f"🐱 {random.choice(PIXEL_ANECDOTES)}")

    # Activité en cours (25% chance)
    if include_activity and random.random() < 0.25:
        time_ctx = get_time_context(hour)
        parts.append(f"📍 En ce moment: {time_ctx['activity']}")

    # Struggle ou good (10% chance, plus fréquent après 50 msgs)
    if include_struggle:
        prob = 0.10 if msg_count < 50 else 0.15
        if random.random() < prob:
            if random.random() < 0.6:  # 60% struggle, 40% good
                parts.append(f"💭 {random.choice(CURRENT_STRUGGLES)}")
            else:
                parts.append(f"✨ {random.choice(CURRENT_GOODS)}")

    # Monday blues
    if day_of_week == 0 and random.random() < 0.3:
        parts.append("😩 C'est lundi, Luna est grumpy")

    # Friday vibes
    if day_of_week == 4 and hour >= 17 and random.random() < 0.3:
        parts.append("🎉 C'est vendredi soir, Luna est de bonne humeur")

    if not parts:
        return None

    return "## CONTEXTE ACTUEL\n" + "\n".join(parts)


def get_luna_situation(hour: int) -> str:
    """Retourne une phrase simple sur la situation de Luna."""
    time_ctx = get_time_context(hour)
    return time_ctx["activity"]
