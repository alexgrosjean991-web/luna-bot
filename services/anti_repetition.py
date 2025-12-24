"""
Anti-Repetition System
----------------------
Évite que Luna répète les mêmes phrases/expressions.

- Track les N dernières réponses par user
- Détecte les patterns répétitifs
- Injecte des instructions pour varier
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cache en mémoire des dernières réponses (reset au restart)
# Format: {user_id: [response1, response2, ...]}
_response_cache: dict[int, list[str]] = defaultdict(list)

MAX_CACHED_RESPONSES = 10

# Phrases/patterns que Luna répète trop souvent
BANNED_PATTERNS = [
    r"t'es adorable",
    r"je suis (là|contente) de te parler",
    r"raconte[- ]moi",
    r"tu me (manques?|plais)",
    r"c'est (trop )?mignon",
    r"t'es (trop )?chou",
    r"j'adore (ça|quand)",
    r"dis[- ]moi",
    r"et toi\s*\?",
    r"ça va\s*\?",
]

# Expressions de transition à varier
TRANSITION_PHRASES = [
    "du coup", "en fait", "genre", "bref", "bon",
    "sinon", "au fait", "tiens", "d'ailleurs"
]


@dataclass
class RepetitionCheck:
    """Résultat du check de répétition."""
    has_repetition: bool
    repeated_phrases: list[str]
    instruction: str | None


def normalize_text(text: str) -> str:
    """Normalise le texte pour comparaison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_phrases(text: str, min_words: int = 3) -> list[str]:
    """Extrait les phrases/segments d'un texte."""
    # Split on common separators
    segments = re.split(r'[.!?\n]+', text)
    phrases = []

    for seg in segments:
        seg = seg.strip()
        words = seg.split()
        if len(words) >= min_words:
            phrases.append(normalize_text(seg))

    return phrases


def add_response(user_id: int, response: str) -> None:
    """Ajoute une réponse au cache."""
    cache = _response_cache[user_id]
    cache.append(response)

    # Keep only last N
    if len(cache) > MAX_CACHED_RESPONSES:
        _response_cache[user_id] = cache[-MAX_CACHED_RESPONSES:]


def check_repetition(user_id: int, new_response: str) -> RepetitionCheck:
    """
    Vérifie si la nouvelle réponse contient des répétitions.

    Returns:
        RepetitionCheck avec les infos de répétition
    """
    cache = _response_cache.get(user_id, [])
    repeated = []

    new_phrases = extract_phrases(new_response)
    new_normalized = normalize_text(new_response)

    # Check against cached responses
    for old_response in cache[-5:]:  # Check last 5 only
        old_normalized = normalize_text(old_response)
        old_phrases = extract_phrases(old_response)

        # Check for exact phrase matches
        for new_phrase in new_phrases:
            if len(new_phrase) > 15:  # Only check substantial phrases
                for old_phrase in old_phrases:
                    if new_phrase in old_phrase or old_phrase in new_phrase:
                        if new_phrase not in repeated:
                            repeated.append(new_phrase)

    # Check for banned patterns
    banned_found = []
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, new_response, re.IGNORECASE):
            # Check if used recently
            for old_response in cache[-3:]:
                if re.search(pattern, old_response, re.IGNORECASE):
                    match = re.search(pattern, new_response, re.IGNORECASE)
                    if match and match.group() not in banned_found:
                        banned_found.append(match.group())
                    break

    repeated.extend(banned_found)

    if repeated:
        instruction = get_anti_repetition_instruction(repeated)
        return RepetitionCheck(
            has_repetition=True,
            repeated_phrases=repeated,
            instruction=instruction
        )

    return RepetitionCheck(
        has_repetition=False,
        repeated_phrases=[],
        instruction=None
    )


def get_anti_repetition_instruction(repeated_phrases: list[str]) -> str:
    """Génère une instruction pour éviter les répétitions."""
    phrases_str = ", ".join(f'"{p}"' for p in repeated_phrases[:3])

    return f"""## ⚠️ ÉVITE LES RÉPÉTITIONS
Tu as déjà utilisé récemment: {phrases_str}
Varie ton vocabulaire! Utilise des formulations différentes.
PAS de "t'es adorable", "raconte-moi", "je suis contente de te parler" en boucle."""


def get_variety_instruction() -> str:
    """Instruction générale pour encourager la variété."""
    return """## VARIÉTÉ
Varie tes expressions! Pas toujours les mêmes phrases.
- Pas "t'es adorable/mignon" à chaque message
- Pas "raconte-moi" en boucle
- Pas "et toi?" systématique
Sois naturelle et spontanée."""


def should_add_variety_reminder(user_id: int) -> bool:
    """Détermine si on doit rappeler de varier (tous les ~10 messages)."""
    cache = _response_cache.get(user_id, [])
    return len(cache) > 0 and len(cache) % 10 == 0


def clear_cache(user_id: int) -> None:
    """Vide le cache pour un user."""
    if user_id in _response_cache:
        del _response_cache[user_id]
