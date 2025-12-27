"""Teasing Progressif - Build-up naturel vers le paywall."""
import random
import logging
from datetime import datetime
from config.settings import settings
PARIS_TZ = settings.PARIS_TZ

logger = logging.getLogger(__name__)

# Build-up progressif du teasing
TEASING_PROGRESSION = {
    2: {
        "type": "innocent",
        "prob": 0.40,
        "messages": [
            "pixel est trop mignon là, j'aurais dû te montrer",
            "j'ai pris une photo de mon café ce matin, trop beau",
        ],
        "proactive": [
            "regarde ce que pixel fait mdrr 🐱",  # Mais pas de vraie photo
        ],
    },
    3: {
        "type": "casual",
        "prob": 0.50,
        "messages": [
            "j'ai failli t'envoyer un selfie mais chui pas maquillée là 😅",
            "tu verrais ma tête ce matin mdrr",
            "j'aurais bien aimé te montrer mon appart",
        ],
        "proactive": [
            "j'ai pris un selfie mais je sais pas si j'ose t'envoyer",
        ],
    },
    4: {
        "type": "suggestive",
        "prob": 0.60,
        "messages": [
            "y'a des photos que j'envoie pas à tout le monde...",
            "j'ai des trucs sur mon tel que je montre à personne 😏",
            "si tu voyais ce que je porte là mdrr",
        ],
        "proactive": [
            "j'ai failli t'envoyer un truc mais... jsp si c'est trop tôt",
        ],
    },
    5: {
        "type": "explicit_tease",
        "prob": 0.70,
        "messages": [
            "j'ai vraiment envie de te montrer des trucs... 😏",
            "y'a des choses que j'aimerais te dire mais pas ici",
            "tu me donnes envie de te montrer plus",
            "j'ai un album que je montre à personne... peut-être un jour",
        ],
        "proactive": [
            "j'ai pensé à toi cette nuit... genre vraiment pensé 😳",
            "j'ai un truc à te dire demain... quelque chose d'important",
        ],
    },
}


def get_teasing_stage(day_count: int) -> str:
    """Retourne le type de teasing pour ce jour."""
    if day_count in TEASING_PROGRESSION:
        return TEASING_PROGRESSION[day_count]["type"]
    return "none"


def should_tease(day_count: int, teasing_count_today: int = 0) -> bool:
    """Décide si on doit teaser."""
    if day_count not in TEASING_PROGRESSION:
        return False

    # Max 1 tease par jour
    if teasing_count_today >= 1:
        return False

    config = TEASING_PROGRESSION[day_count]
    return random.random() < config["prob"]


def get_teasing_message(day_count: int) -> str | None:
    """Retourne un message de teasing pour ce jour."""
    if day_count not in TEASING_PROGRESSION:
        return None

    config = TEASING_PROGRESSION[day_count]
    return random.choice(config["messages"])


def get_teasing_proactive(day_count: int) -> str | None:
    """Retourne un message proactif de teasing."""
    if day_count not in TEASING_PROGRESSION:
        return None

    config = TEASING_PROGRESSION[day_count]
    proactives = config.get("proactive", [])

    if not proactives:
        return None

    return random.choice(proactives)


def get_teasing_instruction(day_count: int) -> str:
    """Retourne des instructions de teasing pour le prompt."""
    if day_count not in TEASING_PROGRESSION:
        return ""

    config = TEASING_PROGRESSION[day_count]
    tease_type = config["type"]

    instructions = {
        "innocent": """
## TEASING LÉGER (optionnel)
Tu peux mentionner des photos de Pixel ou de ton quotidien.
Rien de suggestif, juste créer l'habitude de partager.
""",
        "casual": """
## TEASING CASUAL (optionnel)
Tu peux mentionner que tu aurais aimé lui montrer quelque chose.
"j'ai failli t'envoyer un selfie mais..."
Reste naturelle, pas forcée.
""",
        "suggestive": """
## TEASING SUGGESTIF (optionnel)
Tu peux faire des allusions à des photos/contenus privés.
"y'a des trucs que j'envoie pas à tout le monde..."
Reste mystérieuse, crée l'anticipation.
""",
        "explicit_tease": """
## TEASING EXPLICITE (optionnel)
Tu peux être plus directe sur ton envie de lui montrer plus.
"j'ai vraiment envie de te montrer des trucs..."
Prépare-le à l'idée qu'il y a "plus" à découvrir.
""",
    }

    return instructions.get(tease_type, "")


def check_teasing_opportunity(day_count: int, user_data: dict) -> str | None:
    """Vérifie si c'est le bon moment pour un tease."""
    teasing_stage = user_data.get("teasing_stage", 0)

    # Calcule combien de teases aujourd'hui
    # (simplifié - en prod on regarderait la DB)
    teasing_today = teasing_stage - (day_count - 2) if day_count >= 2 else 0
    teasing_today = max(0, teasing_today)

    if not should_tease(day_count, teasing_today):
        return None

    return get_teasing_message(day_count)
