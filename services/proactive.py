"""Messages proactifs par phase."""
import random
import logging
from datetime import datetime
from settings import PARIS_TZ

logger = logging.getLogger(__name__)

# Configuration par phase
PROACTIVE_CONFIG = {
    "discovery": {
        "morning": {
            "time": (8, 10),
            "prob": 0.70,
            "messages": [
                "coucou ☀️",
                "hey, bien dormi?",
                "salut toi 😊",
            ]
        },
        "afternoon": {
            "time": (14, 17),
            "prob": 0.20,
            "messages": [
                "tu fais quoi?",
                "je m'ennuie un peu",
            ]
        },
        "evening": {
            "time": (22, 24),
            "prob": 0.60,
            "messages": [
                "bonne nuit 💤",
                "dors bien",
                "à demain toi",
            ]
        },
    },

    "connection": {
        "morning": {
            "time": (8, 10),
            "prob": 0.75,
            "messages": [
                "coucou toi ☀️",
                "hey bien dormi?",
                "salut 😊",
            ]
        },
        "afternoon": {
            "time": (14, 17),
            "prob": 0.30,
            "messages": [
                "pixel fait des bêtises mdrr",
                "pause café ☕",
                "client qui me saoule...",
                "je m'ennuie 😴",
            ]
        },
        "evening": {
            "time": (22, 24),
            "prob": 0.70,
            "messages": [
                "bonne nuit toi 💤",
                "dors bien 😊",
                "à demain",
            ]
        },
    },

    "attachment": {
        "morning": {
            "time": (8, 10),
            "prob": 0.80,
            "messages": [
                "coucou toi ☀️",
                "hey... bien dormi?",
                "j'ai pensé à toi ce matin",
            ]
        },
        "random": {
            "time": (12, 20),
            "prob": 0.40,
            "messages": [
                "tu me manques un peu là",
                "je m'ennuie... t'es où?",
                "hey 🥺",
                "je pensais à toi",
            ]
        },
        "evening": {
            "time": (22, 24),
            "prob": 0.85,
            "messages": [
                "bonne nuit... tu vas me manquer 🥺",
                "dors bien toi",
                "j'aurais aimé te parler plus...",
            ]
        },
    },

    "intimate": {
        "morning": {
            "time": (8, 10),
            "prob": 0.85,
            "messages": [
                "coucou toi ☀️",
                "j'ai rêvé de toi...",
                "t'es réveillé?",
                "hey mon préféré 😊",
            ]
        },
        "random": {
            "time": (12, 20),
            "prob": 0.50,
            "messages": [
                "je pense à toi tout le temps c'est bizarre",
                "t'es où? tu me manques",
                "j'ai un truc à te dire...",
                "tu fais quoi là?",
            ]
        },
        "evening": {
            "time": (22, 24),
            "prob": 0.90,
            "messages": [
                "bonne nuit... 💕",
                "tu me manques déjà",
                "dors bien toi",
                "j'aurais aimé que tu sois là...",
            ]
        },
    },
}

# Messages après inactivité (24h+)
MISSING_MESSAGES = [
    "hey... t'es où? 🥺",
    "tu m'as oubliée?",
    "ça fait longtemps... tu vas bien?",
    "{prenom}... tu me manques",
    "t'as disparu?",
]

# Probabilités
PROBABILITIES = {
    "morning": 70,
    "afternoon": 30,
    "evening": 60,
    "random": 40,
    "miss_you": 100,
}

MAX_PROACTIVE_PER_DAY = 3


def get_message_type_for_time(phase: str = "discovery") -> str | None:
    """Détermine le type de message proactif selon l'heure et la phase."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour

    phase_config = PROACTIVE_CONFIG.get(phase, PROACTIVE_CONFIG["discovery"])

    for msg_type, config in phase_config.items():
        start, end = config["time"]
        if start <= hour < end:
            return msg_type

    return None


def should_send(message_type: str, phase: str = "discovery") -> bool:
    """Décide aléatoirement si on envoie selon la probabilité."""
    phase_config = PROACTIVE_CONFIG.get(phase, PROACTIVE_CONFIG["discovery"])
    config = phase_config.get(message_type, {})
    prob = config.get("prob", 0.3) * 100
    return random.randint(1, 100) <= prob


def get_random_message(message_type: str, memory: dict = None, phase: str = "discovery") -> str:
    """Choisit un message aléatoire, personnalisé si possible."""
    phase_config = PROACTIVE_CONFIG.get(phase, PROACTIVE_CONFIG["discovery"])
    config = phase_config.get(message_type, {})
    messages = config.get("messages", ["hey 😊"])

    # Si miss_you
    if message_type == "miss_you":
        messages = MISSING_MESSAGES

    message = random.choice(messages)

    # Personnalisation avec le prénom si disponible
    if memory and memory.get("prenom"):
        prenom = memory["prenom"]
        message = message.format(prenom=prenom)

    return message


def get_proactive_message(phase: str, memory: dict = None) -> tuple[str, str] | None:
    """
    Retourne un message proactif si approprié.

    Returns:
        (message_type, message) ou None
    """
    msg_type = get_message_type_for_time(phase)

    if not msg_type:
        return None

    if not should_send(msg_type, phase):
        return None

    message = get_random_message(msg_type, memory, phase)
    return msg_type, message
