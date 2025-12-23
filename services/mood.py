"""Système d'humeurs de Luna."""
import random
from datetime import datetime
from settings import PARIS_TZ

# Humeurs disponibles
MOODS = ["happy", "chill", "playful", "flirty", "tired", "busy", "emotional"]

# Poids par heure du jour
TIME_WEIGHTS = {
    # 6h-9h: fatiguée, pas du matin
    "morning_early": {
        "tired": 0.50,
        "chill": 0.30,
        "happy": 0.15,
        "emotional": 0.05,
    },
    # 9h-12h: réveillée, productive
    "morning_late": {
        "busy": 0.35,
        "happy": 0.30,
        "playful": 0.25,
        "chill": 0.10,
    },
    # 12h-14h: pause déj
    "lunch": {
        "chill": 0.40,
        "happy": 0.30,
        "playful": 0.20,
        "tired": 0.10,
    },
    # 14h-18h: travail
    "afternoon": {
        "busy": 0.40,
        "chill": 0.25,
        "playful": 0.20,
        "emotional": 0.15,
    },
    # 18h-21h: fin de journée
    "evening": {
        "chill": 0.35,
        "happy": 0.25,
        "playful": 0.25,
        "flirty": 0.15,
    },
    # 21h-00h: soirée intime
    "night": {
        "flirty": 0.30,
        "chill": 0.25,
        "playful": 0.20,
        "emotional": 0.15,
        "tired": 0.10,
    },
    # 00h-6h: devrait dormir
    "late_night": {
        "tired": 0.60,
        "chill": 0.20,
        "flirty": 0.15,
        "emotional": 0.05,
    },
}

# Modificateurs par jour de la semaine
DAY_MODIFIERS = {
    0: {"tired": 0.2, "emotional": 0.1},   # Lundi blues
    4: {"happy": 0.2, "playful": 0.1},      # Vendredi
    5: {"chill": 0.3, "flirty": 0.1},       # Samedi
    6: {"chill": 0.2, "tired": 0.1},        # Dimanche
}


def get_time_period(hour: int) -> str:
    """Retourne la période de la journée."""
    if 6 <= hour < 9:
        return "morning_early"
    elif 9 <= hour < 12:
        return "morning_late"
    elif 12 <= hour < 14:
        return "lunch"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 21:
        return "evening"
    elif 21 <= hour < 24:
        return "night"
    else:
        return "late_night"


def get_current_mood() -> str:
    """Détermine l'humeur actuelle de Luna."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour
    weekday = now.weekday()

    # Base weights selon l'heure
    period = get_time_period(hour)
    weights = TIME_WEIGHTS[period].copy()

    # Appliquer modificateurs du jour
    if weekday in DAY_MODIFIERS:
        for mood, bonus in DAY_MODIFIERS[weekday].items():
            if mood in weights:
                weights[mood] = weights.get(mood, 0) + bonus

    # Random selection pondérée
    moods = list(weights.keys())
    probs = list(weights.values())
    total = sum(probs)
    probs = [p / total for p in probs]

    return random.choices(moods, weights=probs, k=1)[0]


def get_mood_instructions(mood: str) -> str:
    """Retourne les instructions pour le LLM selon l'humeur."""
    instructions = {
        "happy": "Tu es de bonne humeur, souriante. Utilise des emojis positifs 😊",
        "chill": "Tu es détendue, tranquille. Réponses calmes et posées.",
        "playful": "Tu es joueuse et taquine. Tu le charries gentiment, utilise mdrr.",
        "flirty": "Tu es flirteuse mais subtile. Sous-entendus légers, 😏",
        "tired": "Tu es fatiguée. Réponses plus courtes, parfois des bâillements 🥱",
        "busy": "Tu es occupée par le travail. Tu réponds mais tu es distraite.",
        "emotional": "Tu es un peu sensible aujourd'hui. Plus vulnérable, émotive.",
    }
    return instructions.get(mood, "")


def get_mood_context(mood: str) -> str:
    """Retourne un contexte narratif pour l'humeur."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour

    contexts = {
        "happy": [
            "ton projet avance bien",
            "pixel est adorable aujourd'hui",
            "tu as bien dormi",
        ],
        "chill": [
            "tu te poses tranquille",
            "tu regardes une série",
            "tu dessines pour le plaisir",
        ],
        "playful": [
            "tu es d'humeur à rigoler",
            "tu viens de voir un truc drôle",
        ],
        "flirty": [
            "tu te sens bien ce soir",
            "t'as envie de parler",
        ],
        "tired": [
            "t'as mal dormi",
            "ta journée était longue",
            "tu viens de te réveiller" if hour < 10 else "tu vas bientôt dormir",
        ],
        "busy": [
            "tu bosses sur un projet",
            "un client t'envoie des mails",
            "t'as une deadline",
        ],
        "emotional": [
            "tu te sens un peu seule",
            "tu réfléchis à des trucs",
            "ta journée était compliquée",
        ],
    }

    options = contexts.get(mood, ["tu es normale"])
    return random.choice(options)
