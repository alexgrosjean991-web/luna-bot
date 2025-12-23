import httpx
import logging
import random
from typing import List, Dict, Optional
from config.settings import config
from src.services.response_filter import response_filter

logger = logging.getLogger(__name__)


class LLMService:
    """Handles LLM API calls - Anthropic for SFW, OpenRouter for NSFW"""

    # Keywords that make Haiku refuse
    NSFW_KEYWORDS = [
        "bite", "cock", "dick", "chatte", "pussy", "sucer", "suck",
        "baise", "fuck", "jouir", "cum", "gémis", "moan", "orgasm",
        "nu", "naked", "déshabille", "undress", "sexe", "sex",
        "caresse", "touche", "embrasse", "corps contre", "peau contre",
        "mmh", "aah", "frisson", "excit", "mouillé", "bandant",
        "string", "culotte", "soutif", "seins", "nichons"
    ]

    def __init__(self):
        self.anthropic_url = "https://api.anthropic.com/v1/messages"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"

    def _sanitize_history_for_haiku(self, messages: List[Dict]) -> List[Dict]:
        """
        Sanitize history for Haiku to prevent refusals.
        Removes messages containing NSFW content.
        """
        safe_messages = []
        for msg in messages:
            content = msg.get('content', '').lower()
            is_nsfw = any(kw in content for kw in self.NSFW_KEYWORDS)
            if not is_nsfw:
                safe_messages.append(msg)

        # Si trop de messages filtrés, garder juste les 3 derniers safe
        if len(safe_messages) < 3 and len(messages) > 0:
            # Fallback: garder le dernier message user seulement
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    content = msg.get('content', '').lower()
                    if not any(kw in content for kw in self.NSFW_KEYWORDS):
                        return [msg]
            # Dernier recours: message vide
            return [{"role": "user", "content": "hey"}]

        logger.info(f"History sanitized: {len(messages)} -> {len(safe_messages)} messages")
        return safe_messages

    async def generate_response(self, system_prompt: str, messages: List[Dict],
                                  is_nsfw: bool = False, is_french: bool = True) -> str:
        """Generate response using appropriate model"""

        if is_nsfw:
            logger.info("🔥 CALLING DOLPHIN (OpenRouter)")
            response = await self._call_openrouter(system_prompt, messages, is_french)
        else:
            logger.info("💬 CALLING HAIKU (Anthropic)")
            # Sanitize history to prevent refusals
            safe_messages = self._sanitize_history_for_haiku(messages)
            response = await self._call_anthropic(system_prompt, safe_messages, is_french)

        # Appliquer le ResponseFilter (refus AI, actions, emojis, etc.)
        response = response_filter.filter(response, is_french=is_french, max_emojis=2)

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
            "max_tokens": 500,
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
            from src.services.response_filter import ResponseFilter
            fallback = random.choice(ResponseFilter.FRENCH_FALLBACKS if is_french else ResponseFilter.ENGLISH_FALLBACKS)
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
            "max_tokens": 150  # Force short responses
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
            from src.services.response_filter import ResponseFilter
            fallback = random.choice(ResponseFilter.FRENCH_FALLBACKS if is_french else ResponseFilter.ENGLISH_FALLBACKS)
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
