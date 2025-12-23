"""
ResponseFilter - Sanitizes LLM responses for immersion
Removes AI artifacts, limits emojis, cleans formatting
"""

import re
import random
import logging

logger = logging.getLogger(__name__)


class ResponseFilter:
    """Filtre les réponses LLM pour maintenir l'immersion"""

    # Patterns de refus AI à détecter
    AI_REFUSAL_PATTERNS = [
        # English refusals
        "i cannot", "i can't", "i will not", "i won't",
        "i do not feel comfortable", "i don't feel comfortable",
        "not comfortable", "not appropriate",
        "i'm not able", "i am not able",
        "as an ai", "as a language model",
        "i must maintain", "i need to maintain",
        "this conversation", "this type of",
        "boundaries", "ethical",
        # French refusals
        "je ne peux pas", "je ne suis pas en mesure",
        "je ne suis pas à l'aise", "pas approprié",
        "en tant qu'ia", "en tant que",
        "je dois maintenir", "limites",
    ]

    # Fallbacks naturels
    FRENCH_FALLBACKS = [
        "hmmm doucement bb 😏",
        "tu me fais rougir là 🙈",
        "t'es chaud toi... j'aime bien",
        "hm patience...",
        "on a le temps non? 😏",
        "jsp si j'ose...",
    ]

    ENGLISH_FALLBACKS = [
        "hmmm slow down babe 😏",
        "youre making me blush 🙈",
        "youre bold... i kinda like it",
        "hm patience...",
        "we have time right? 😏",
        "idk if i dare...",
    ]

    # Emoji pattern - match SINGLE emojis (no + at end)
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended
        "]",
        flags=re.UNICODE
    )

    @classmethod
    def filter(cls, response: str, is_french: bool = True, max_emojis: int = 1) -> str:
        """
        Filtre complet de la réponse LLM

        1. Détecte et remplace les refus AI
        2. Supprime le markdown (*bold*, _italic_)
        3. Limite le nombre d'emojis
        4. Nettoie les artifacts
        """

        original = response

        # 1. Détecter les refus AI
        response = cls._handle_ai_refusal(response, is_french)
        if response != original:
            logger.info(f"🚫 AI refusal replaced with fallback")
            return response  # Fallback déjà propre, pas besoin de filtrer

        # 2. Supprimer le markdown
        response = cls._remove_markdown(response)

        # 3. Limiter les emojis
        response = cls._limit_emojis(response, max_emojis)

        # 4. Nettoyer les artifacts
        response = cls._clean_artifacts(response)

        if response != original:
            logger.debug(f"Response filtered: '{original[:50]}...' -> '{response[:50]}...'")

        return response

    @classmethod
    def _handle_ai_refusal(cls, response: str, is_french: bool) -> str:
        """Détecte et remplace les refus style AI"""

        response_lower = response.lower()

        is_refusal = any(pattern in response_lower for pattern in cls.AI_REFUSAL_PATTERNS)

        if is_refusal:
            logger.warning(f"⚠️ AI REFUSAL DETECTED: {response[:100]}...")
            fallback = random.choice(cls.FRENCH_FALLBACKS if is_french else cls.ENGLISH_FALLBACKS)
            logger.info(f"✅ Replaced with fallback: {fallback}")
            return fallback

        return response

    @classmethod
    def _remove_markdown(cls, response: str) -> str:
        """Supprime le formatage markdown (*bold*, _italic_, etc.)"""

        # *bold* ou **bold** → bold
        response = re.sub(r'\*\*(.+?)\*\*', r'\1', response)
        response = re.sub(r'\*(.+?)\*', r'\1', response)

        # _italic_ ou __italic__ → italic
        response = re.sub(r'__(.+?)__', r'\1', response)
        response = re.sub(r'_(.+?)_', r'\1', response)

        # `code` → code
        response = re.sub(r'`(.+?)`', r'\1', response)

        # # Headers → text
        response = re.sub(r'^#+\s*', '', response, flags=re.MULTILINE)

        # - bullet points → text (mais garder le tiret simple)
        response = re.sub(r'^\s*[-*]\s+', '', response, flags=re.MULTILINE)

        return response

    @classmethod
    def _limit_emojis(cls, response: str, max_emojis: int = 1) -> str:
        """Limite le nombre d'emojis dans la réponse"""

        # Trouver tous les emojis avec leurs positions
        emoji_matches = list(cls.EMOJI_PATTERN.finditer(response))

        if len(emoji_matches) <= max_emojis:
            return response

        # Supprimer les emojis après le Nème
        result = response
        emojis_to_remove = emoji_matches[max_emojis:]

        # Supprimer en ordre inverse pour ne pas décaler les positions
        for match in reversed(emojis_to_remove):
            result = result[:match.start()] + result[match.end():]

        logger.debug(f"Emoji limited: {len(emoji_matches)} -> {max_emojis}")

        return result

    @classmethod
    def _clean_artifacts(cls, response: str) -> str:
        """Nettoie les artifacts courants des LLM"""

        # Supprimer les espaces multiples
        response = re.sub(r' +', ' ', response)

        # Supprimer les retours à la ligne multiples
        response = re.sub(r'\n\n+', '\n', response)

        # Supprimer les espaces en début/fin
        response = response.strip()

        # Supprimer les guillemets autour de la réponse entière
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        if response.startswith("'") and response.endswith("'"):
            response = response[1:-1]

        return response


# Instance globale
response_filter = ResponseFilter()
