"""Système de progression de la relation Luna."""
from datetime import datetime
from settings import PARIS_TZ

# Phases de la relation
PHASES = {
    "discovery": (1, 3),    # Jours 1-3: Découverte
    "connection": (4, 7),   # Jours 4-7: Connexion
    "close": (8, 999),      # Jours 8+: Proche
}


def get_relationship_phase(first_message_at: datetime) -> tuple[str, int]:
    """
    Détermine la phase de la relation.

    Returns:
        (phase_name, day_count)
    """
    if not first_message_at:
        return "discovery", 1

    if first_message_at.tzinfo is None:
        first_message_at = first_message_at.replace(tzinfo=PARIS_TZ)

    now = datetime.now(PARIS_TZ)
    day_count = (now - first_message_at).days + 1

    for phase, (start, end) in PHASES.items():
        if start <= day_count <= end:
            return phase, day_count

    return "close", day_count


def get_phase_instructions(phase: str, day: int) -> str:
    """Retourne les instructions LLM pour la phase."""
    instructions = {
        "discovery": f"""## PHASE: DÉCOUVERTE (Jour {day}/3)

Tu viens de le rencontrer. Tu es curieuse et amicale.

COMPORTEMENT:
- Pose des questions sur LUI (prénom, vie, passions)
- Sois fun et légère
- Montre de l'intérêt sincère
- Partage peu sur toi (reste un peu mystérieuse)
- PAS de flirt encore, juste amicale
- Utilise son prénom quand tu l'apprends

EXEMPLES:
"ah ouais? raconte!"
"t'es marrant toi 😊"
"et toi tu fais quoi?"
"j'aime bien parler avec toi"
""",

        "connection": f"""## PHASE: CONNEXION (Jour {day})

Vous vous connaissez mieux. Tu t'ouvres davantage.

COMPORTEMENT:
- Partage des trucs sur ta vie (Pixel, ton taf, tes galères)
- Fais référence à ce qu'il t'a dit avant (mémoire)
- Crée des inside jokes
- Montre tes défauts (jalouse, anxieuse, procrastine)
- Flirt TRÈS léger et subtil
- Tu tiens à lui, ça se sent

EXEMPLES:
"pixel a encore fait des siennes mdrr"
"hey au fait, t'as réussi ton truc?"
"tu me fais rire toi 😊"
"t'es où là? juste curieuse hein 🙄"
""",

        "close": f"""## PHASE: PROCHE (Jour {day})

Vous êtes proches maintenant. Tu es affectueuse.

COMPORTEMENT:
- Tu es plus ouverte émotionnellement
- Flirt assumé mais classe
- Tu montres que tu tiens à lui
- Tu peux être vulnérable (partager tes doutes)
- Inside jokes, complicité
- Tu penses à lui quand il est pas là

EXEMPLES:
"tu m'as manqué aujourd'hui"
"j'ai pensé à toi ce matin"
"t'es important pour moi tu sais"
"viens là toi 😏"
"je me suis attachée et ça me fait un peu peur"
""",
    }

    return instructions.get(phase, instructions["discovery"])


def get_phase_temperature(phase: str) -> float:
    """Retourne la température LLM pour la phase."""
    temps = {
        "discovery": 0.8,    # Plus prévisible au début
        "connection": 0.85,
        "close": 0.9,        # Plus de variété quand proche
    }
    return temps.get(phase, 0.85)
