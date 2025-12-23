import httpx
import logging
import random
from typing import List, Dict, Optional
from config.settings import config

logger = logging.getLogger(__name__)

# Fallbacks EN FRANÇAIS pour les refus
FRENCH_FALLBACKS = [
    "hmmm doucement bb 😏 on a le temps...",
    "tu me fais rougir là... 🙈",
    "attends j'ai bugé mdr... tu disais?",
    "oula mon tel a lagué, redis moi ça 😏",
    "hm j'ai pas capté, redis?",
    "mdr t'es chaud toi... j'aime bien 😏",
]

ENGLISH_FALLBACKS = [
    "hmmm slow down babe 😏 we have time...",
    "youre making me blush... 🙈",
    "wait my phone glitched lol... what were you saying?",
    "ugh my phone lagged, say that again 😏",
    "hm i didnt catch that, say again?",
    "lol youre bold... i kinda like it 😏",
]

class LLMService:
    """Handles LLM API calls - Anthropic for SFW, OpenRouter for NSFW"""

    def __init__(self):
        self.anthropic_url = "https://api.anthropic.com/v1/messages"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
    
    async def generate_response(self, system_prompt: str, messages: List[Dict],
                                  is_nsfw: bool = False, is_french: bool = True) -> str:
        """Generate response using appropriate model"""

        if is_nsfw:
            logger.info("🔥 CALLING DOLPHIN (OpenRouter)")
            response = await self._call_openrouter(system_prompt, messages, is_french)
        else:
            logger.info("💬 CALLING HAIKU (Anthropic)")
            response = await self._call_anthropic(system_prompt, messages, is_french)

        # Détecter les refus AI et remplacer par fallback
        response = self._sanitize_ai_refusal(response, is_french)

        return response

    def _sanitize_ai_refusal(self, response: str, is_french: bool) -> str:
        """Détecte et remplace les refus style AI par des fallbacks naturels"""

        # Patterns de refus AI à détecter
        ai_refusal_patterns = [
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

        response_lower = response.lower()

        # Check for refusal patterns
        is_refusal = any(pattern in response_lower for pattern in ai_refusal_patterns)

        if is_refusal:
            logger.warning(f"⚠️ AI REFUSAL DETECTED: {response[:100]}...")
            fallback = random.choice(FRENCH_FALLBACKS if is_french else ENGLISH_FALLBACKS)
            logger.info(f"✅ Replaced with fallback: {fallback}")
            return fallback

        return response
    
    async def _call_anthropic(self, system_prompt: str, messages: List[Dict], is_french: bool = True) -> str:
        """Call Anthropic Claude API"""

        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Convert messages to Anthropic format
        api_messages = []
        for msg in messages[-20:]:  # Last 20 messages
            role = "user" if msg.get("role") == "user" else "assistant"
            api_messages.append({"role": role, "content": msg["content"]})

        payload = {
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": 300,
            "system": system_prompt,
            "messages": api_messages
        }

        # === DEBUG LOGGING ===
        logger.info(f"=== HAIKU REQUEST ===")
        logger.info(f"Model: {config.ANTHROPIC_MODEL}")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        logger.info(f"Messages count: {len(api_messages)}")
        if api_messages:
            last_msg = api_messages[-1]
            logger.info(f"Last message: {last_msg['role']}: {last_msg['content'][:100]}...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.anthropic_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                result = data["content"][0]["text"]
                logger.info(f"=== HAIKU RESPONSE ===")
                logger.info(f"Response: {result[:200]}...")
                return result
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            fallback = random.choice(FRENCH_FALLBACKS if is_french else ENGLISH_FALLBACKS)
            return fallback
    
    async def _call_openrouter(self, system_prompt: str, messages: List[Dict], is_french: bool = True) -> str:
        """Call OpenRouter API for NSFW content (Dolphin)"""

        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        # Convert messages to OpenAI format
        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages[-20:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            api_messages.append({"role": role, "content": msg["content"]})

        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": api_messages,
            "max_tokens": 400
        }

        # === DEBUG LOGGING ===
        logger.info(f"=== DOLPHIN REQUEST ===")
        logger.info(f"Model: {config.OPENROUTER_MODEL}")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        logger.info(f"Messages count: {len(api_messages)}")
        if len(api_messages) > 1:
            last_msg = api_messages[-1]
            logger.info(f"Last message: {last_msg['role']}: {last_msg['content'][:100]}...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.openrouter_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                logger.info(f"=== DOLPHIN RESPONSE ===")
                logger.info(f"Response: {result[:200]}...")
                return result
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            fallback = random.choice(FRENCH_FALLBACKS if is_french else ENGLISH_FALLBACKS)
            return fallback
    
    def detect_nsfw(self, text: str) -> bool:
        """Detect if message is NSFW"""
        nsfw_keywords = [
            "nude", "naked", "sex", "fuck", "dick", "cock", "pussy",
            "undress", "strip", "horny", "cum", "suck", "lick",
            "nue", "nu", "sexe", "baise", "bite", "chatte"
        ]
        
        text_lower = text.lower()
        return any(kw in text_lower for kw in nsfw_keywords)


llm_service = LLMService()
