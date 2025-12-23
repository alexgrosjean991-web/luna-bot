"""
ResponseFilter - Sanitizes LLM responses for immersion
Removes AI artifacts, limits emojis, cleans formatting
"""

import re
import random
import logging

logger = logging.getLogger(__name__)


class ResponseFilter:
    """Filtre les réponses LLM pour maintenir l'immersion parfaite"""

    # Patterns de refus AI à détecter
    AI_REFUSAL_PATTERNS = [
        # English refusals
        "i cannot", "i can't", "i will not", "i won't",
        "i do not feel comfortable", "i don't feel comfortable",
        "not comfortable", "not appropriate",
        "i'm not able", "i am not able",
        "as an ai", "as a language model", "as an assistant",
        "i must maintain", "i need to maintain",
        "this conversation", "this type of",
        "boundaries", "ethical", "guidelines",
        "i'm programmed", "i am programmed",
        # French refusals
        "je ne peux pas", "je ne suis pas en mesure",
        "je ne suis pas à l'aise", "pas approprié",
        "en tant qu'ia", "en tant qu'intelligence artificielle",
        "en tant que", "je suis une ia", "je suis une intelligence artificielle",
        "je dois maintenir", "limites", "programmé",
        "j'ai bugé", "j'ai bug", "bug", "glitch",
        "modèle de langage", "assistant virtuel",
    ]

    # Phrases bannies (à supprimer complètement)
    BANNED_PHRASES = [
        "en tant qu'ia",
        "en tant qu'intelligence artificielle",
        "je suis une intelligence artificielle",
        "je suis une ia",
        "je suis un assistant",
        "j'ai bugé",
        "j'ai bug",
        "redis moi",
        "reformule",
        "je ne comprends pas ta question",
        "en quoi puis-je t'aider",
        "comment puis-je t'aider",
        "je suis là pour t'aider",
        "n'hésite pas à me demander",
    ]

    # Phrases NSFW passives à supprimer (questions qui cassent le flow)
    NSFW_PASSIVE_PATTERNS = [
        "dis-moi ce que tu veux",
        "dis moi ce que tu veux",
        "qu'est-ce que tu aimerais",
        "qu'est-ce que tu voudrais",
        "que veux-tu faire",
        "que voudrais-tu",
        "qu'est-ce qui te ferait plaisir",
        "quel est ton fantasme",
        "quels sont tes fantasmes",
        "tu voudrais faire quoi",
        "tu veux faire quoi",
        "qu'est-ce que tu aimerais sentir",
        "keske tu aimerais",
        "keske tu voudrais",
        "dis-moi ce qui te ferait",
        "dis moi ce qui te ferait",
        "est-ce que c'est ce que tu voulais",
        "c'est ce que tu voulais",
        "tu veux que je",
        "tu ne crois pas",
        "tu ne penses pas",
    ]

    # Fallbacks naturels
    FRENCH_FALLBACKS = [
        "hmmm 😏",
        "tu me fais rougir 🙈",
        "t'es chaud toi...",
        "hm patience",
        "on a le temps",
        "jsp si j'ose",
        "attends j'réfléchis",
        "hmm laisse moi réfléchir",
    ]

    ENGLISH_FALLBACKS = [
        "hmmm 😏",
        "youre making me blush 🙈",
        "youre bold...",
        "hm patience",
        "we have time",
        "idk if i dare",
        "wait let me think",
        "hmm let me think",
    ]

    # Emoji pattern - match SINGLE emojis
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

    # Pattern pour les actions *action* - à SUPPRIMER complètement
    ACTION_PATTERN = re.compile(r'\*[^*]+\*')

    @classmethod
    def filter(cls, response: str, is_french: bool = True, max_emojis: int = 2) -> str:
        """
        Filtre complet de la réponse LLM

        1. Détecte et remplace les refus AI
        2. Supprime les actions *action*
        3. Supprime les phrases bannies
        4. Limite le nombre d'emojis
        5. Nettoie les artifacts
        """

        original = response

        # 1. Détecter les refus AI
        response = cls._handle_ai_refusal(response, is_french)
        if response != original:
            logger.info(f"🚫 AI refusal replaced with fallback")
            return response  # Fallback déjà propre

        # 2. Supprimer les actions *action*
        response = cls._remove_actions(response)

        # 3. Supprimer les phrases bannies
        response = cls._remove_banned_phrases(response)

        # 3.5 Supprimer les questions passives NSFW
        response = cls._remove_nsfw_passive(response)

        # 4. Limiter les emojis
        response = cls._limit_emojis(response, max_emojis)

        # 5. Nettoyer les artifacts
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
    def _remove_actions(cls, response: str) -> str:
        """Supprime les actions entre astérisques *action*"""

        # Trouver et supprimer toutes les actions
        actions_found = cls.ACTION_PATTERN.findall(response)

        if actions_found:
            response = cls.ACTION_PATTERN.sub('', response)
            logger.debug(f"Removed {len(actions_found)} actions: {actions_found}")

        return response

    @classmethod
    def _remove_banned_phrases(cls, response: str) -> str:
        """Supprime les phrases bannies de la réponse"""

        response_lower = response.lower()

        for phrase in cls.BANNED_PHRASES:
            if phrase in response_lower:
                # Supprimer la phrase (case insensitive)
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                response = pattern.sub('', response)
                logger.debug(f"Removed banned phrase: {phrase}")

        return response

    @classmethod
    def _remove_nsfw_passive(cls, response: str) -> str:
        """Supprime les questions passives qui cassent le flow NSFW"""

        response_lower = response.lower()
        original = response

        for pattern in cls.NSFW_PASSIVE_PATTERNS:
            if pattern in response_lower:
                # Trouver et supprimer la phrase entière jusqu'au ?
                regex = re.compile(
                    re.escape(pattern) + r'[^.!?\n]*[?]?',
                    re.IGNORECASE
                )
                response = regex.sub('', response)
                logger.info(f"🚫 Removed NSFW passive question: {pattern}")

        if response != original:
            # Nettoyer les espaces et ponctuation orpheline
            response = re.sub(r'\s+', ' ', response)
            response = re.sub(r'^\s*[.,;:]\s*', '', response)
            response = response.strip()

        return response

    @classmethod
    def _limit_emojis(cls, response: str, max_emojis: int = 2) -> str:
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

        # === SUPPRIMER LES CARACTÈRES NON-LATINS (russe, chinois, etc.) ===
        # Garde: Latin, accents français, emojis, ponctuation
        response = re.sub(r'[а-яА-ЯёЁ\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', '', response)

        # === SUPPRIMER TOUS LES ASTÉRISQUES ===
        # Luna n'utilise JAMAIS d'astérisques (ni pour actions ni pour emphase)
        response = response.replace('*', '')

        # === SUPPRIMER LES HALLUCINATIONS/GIBBERISH EN FIN DE MESSAGE ===
        # Pattern: texte random après un emoji ou ponctuation finale
        # Ex: "mmh... 😏 dire ouais c etou vas" -> "mmh... 😏"
        gibberish_patterns = [
            r'\s+dire\s+\w+.*$',  # "dire ouais, c etou..."
            r'\s+c\s+etou.*$',
            r'\s+trop\s+liter.*$',
            r'\s+tu\s+peux\s+optimis.*$',
            r'\s+wtf.*$',
            r'\s+\[.*\].*$',  # "[something]"
            r'\s+At\s+\d{4}-.*$',  # "At 0000-00-00..."
        ]
        for pattern in gibberish_patterns:
            response = re.sub(pattern, '', response, flags=re.IGNORECASE)

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

        # Supprimer les tirets ou points en début de message
        response = re.sub(r'^[-•]\s*', '', response)

        # Nettoyer les espaces autour de la ponctuation
        response = re.sub(r'\s+([.,!?])', r'\1', response)
        response = re.sub(r'([.,!?])\s+', r'\1 ', response)

        # Nettoyer les virgules doublées ou mal placées (,, ou , ,)
        response = re.sub(r',\s*,', ',', response)

        return response.strip()


# Instance globale
response_filter = ResponseFilter()
