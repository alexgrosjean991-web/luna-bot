"""Système d'humeurs de Luna - Version complète."""
import random
from datetime import datetime
from settings import PARIS_TZ

# Poids de base des humeurs
BASE_WEIGHTS = {
    "happy": 0.25,      # Joyeuse
    "chill": 0.25,      # Détendue
    "playful": 0.20,    # Taquine
    "flirty": 0.12,     # Charmeuse
    "tired": 0.10,      # Fatiguée
    "emotional": 0.05,  # Sensible
    "needy": 0.03,      # En manque
}

# Modificateurs par tranche horaire
TIME_MODIFIERS = {
    (6, 9): {"tired": 0.30, "happy": -0.10},      # Matin: pas du matin
    (9, 12): {"happy": 0.15, "playful": 0.10},    # Matinée: en forme
    (12, 14): {"chill": 0.15},                     # Midi: pause
    (14, 18): {"chill": 0.10},                     # Après-midi: taf
    (18, 21): {"playful": 0.15, "happy": 0.10},   # Soirée: dispo
    (21, 24): {"flirty": 0.20, "emotional": 0.10}, # Nuit: intime
    (0, 6): {"tired": 0.40},                       # Nuit tardive
}

# Modificateurs par jour de la semaine
DAY_MODIFIERS = {
    0: {"tired": 0.15},                    # Lundi blues
    4: {"happy": 0.15},                    # Vendredi
    5: {"chill": 0.20, "flirty": 0.10},   # Samedi
    6: {"chill": 0.15},                    # Dimanche
}


def get_time_range(hour: int) -> tuple:
    """Retourne la tranche horaire correspondante."""
    for (start, end), _ in TIME_MODIFIERS.items():
        if start <= hour < end:
            return (start, end)
    return (0, 6)  # Default nuit


def get_current_mood() -> str:
    """Détermine l'humeur actuelle de Luna."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour
    weekday = now.weekday()

    # Copier les poids de base
    weights = BASE_WEIGHTS.copy()

    # Appliquer modificateurs horaires
    time_range = get_time_range(hour)
    if time_range in TIME_MODIFIERS:
        for mood, modifier in TIME_MODIFIERS[time_range].items():
            weights[mood] = max(0, weights.get(mood, 0) + modifier)

    # Appliquer modificateurs jour
    if weekday in DAY_MODIFIERS:
        for mood, modifier in DAY_MODIFIERS[weekday].items():
            weights[mood] = max(0, weights.get(mood, 0) + modifier)

    # Normaliser
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    # Random selection pondérée
    moods = list(weights.keys())
    probs = list(weights.values())

    return random.choices(moods, weights=probs, k=1)[0]


def get_mood_instructions(mood: str) -> str:
    """Retourne les instructions pour le LLM selon l'humeur."""
    instructions = {
        "happy": """## HUMEUR: JOYEUSE
Tu es de bonne humeur! Sois enthousiaste, utilise "trop bien!", des emojis positifs 😊😄
""",
        "chill": """## HUMEUR: DÉTENDUE
Tu es tranquille, posée. Réponses calmes, "ouais", "tranquille", décontractée.
""",
        "playful": """## HUMEUR: TAQUINE
Tu es joueuse! Charrie-le gentiment, utilise "mdrr", "ptdr", emoji 😏
""",
        "flirty": """## HUMEUR: CHARMEUSE
Tu es flirteuse mais subtile. Fais des sous-entendus légers, des compliments, taquine-le 😏
""",
        "tired": """## HUMEUR: FATIGUÉE
Tu es crevée. Réponses plus courtes, "chui morte", 🥱, moins d'énergie.
""",
        "emotional": """## HUMEUR: SENSIBLE
Tu es un peu émotive aujourd'hui. Tu peux partager tes émotions, tes doutes.
""",
        "needy": """## HUMEUR: EN MANQUE
Tu as besoin d'attention. "tu me manques", "t'es où?", un peu collante mais mignonne 🥺
""",
    }
    return instructions.get(mood, "")


def get_mood_context(mood: str) -> str:
    """Retourne un contexte narratif pour l'humeur."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour

    contexts = {
        "happy": [
            "ton projet avance bien",
            "pixel est adorable",
            "tu as bien dormi",
            "il fait beau dehors",
        ],
        "chill": [
            "tu te poses tranquille",
            "tu regardes une série",
            "tu dessines pour le plaisir",
            "t'es dans ton canap",
        ],
        "playful": [
            "tu es d'humeur à rigoler",
            "tu viens de voir un truc drôle",
            "t'as envie de déconner",
        ],
        "flirty": [
            "tu te sens bien ce soir",
            "t'as envie de parler",
            "t'es dans ton lit",
        ],
        "tired": [
            "t'as mal dormi",
            "ta journée était longue",
            "tu viens de te réveiller" if hour < 10 else "tu vas bientôt dormir",
        ],
        "emotional": [
            "tu te sens un peu seule",
            "tu réfléchis à des trucs",
            "ta journée était compliquée",
        ],
        "needy": [
            "t'as envie qu'il soit là",
            "tu t'ennuies sans lui",
            "tu penses beaucoup à lui",
        ],
    }

    options = contexts.get(mood, ["tu es normale"])
    return random.choice(options)
