"""Messages proactifs automatiques."""
import random
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Timezone Paris (UTC+1)
PARIS_TZ = timezone(timedelta(hours=1))

# Messages templates par type
MESSAGES = {
    "morning": [
        "coucou toi ☀️",
        "bonjour 😊",
        "bien dormi?",
        "hello, debout? 🥱",
        "cc, bonne journée à toi",
    ],
    "night": [
        "bonne nuit 💤",
        "je vais dormir, bisous",
        "dors bien toi 😴",
        "nuit nuit",
        "je vais me coucher, pense à moi 😏",
    ],
    "miss_you": [
        "t'es où... 🥺",
        "tu me manques un peu",
        "hey ça fait longtemps",
        "t'as disparu?",
        "jme fais du souci là",
    ],
    "random": [
        "pixel fait n'importe quoi là mdrr",
        "je procrastine grave 🙄",
        "j'ai faim",
        "je m'ennuie un peu",
        "tu fais quoi toi",
        "j'ai pensé à toi",
    ],
}

# Probabilités par type (0-100)
PROBABILITIES = {
    "morning": 70,
    "night": 50,
    "miss_you": 100,
    "random": 30,
}

MAX_PROACTIVE_PER_DAY = 2


def get_message_type_for_time() -> str | None:
    """Détermine le type de message proactif selon l'heure actuelle."""
    now = datetime.now(PARIS_TZ)
    hour = now.hour

    if 8 <= hour < 10:
        return "morning"
    elif 22 <= hour or hour < 1:
        return "night"
    elif 14 <= hour < 18:
        return "random"

    return None


def should_send(message_type: str) -> bool:
    """Décide aléatoirement si on envoie selon la probabilité."""
    prob = PROBABILITIES.get(message_type, 0)
    return random.randint(1, 100) <= prob


def get_random_message(message_type: str, memory: dict = None) -> str:
    """Choisit un message aléatoire, personnalisé si possible."""
    messages = MESSAGES.get(message_type, ["hey"])
    message = random.choice(messages)

    # Personnalisation avec le prénom si disponible
    if memory and memory.get("prenom"):
        prenom = memory["prenom"]
        if random.random() < 0.3:
            if message_type == "morning":
                message = f"coucou {prenom} ☀️"
            elif message_type == "miss_you":
                message = f"{prenom}... t'es où? 🥺"

    return message
