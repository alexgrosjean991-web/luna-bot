import httpx
import logging
from typing import List, Dict, Optional
from config.settings import config

logger = logging.getLogger(__name__)

class LLMService:
    """Handles LLM API calls - Anthropic for SFW, OpenRouter for NSFW"""
    
    def __init__(self):
        self.anthropic_url = "https://api.anthropic.com/v1/messages"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
    
    async def generate_response(self, system_prompt: str, messages: List[Dict],
                                  is_nsfw: bool = False) -> str:
        """Generate response using appropriate model"""
        
        if is_nsfw:
            return await self._call_openrouter(system_prompt, messages)
        else:
            return await self._call_anthropic(system_prompt, messages)
    
    async def _call_anthropic(self, system_prompt: str, messages: List[Dict]) -> str:
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
        logger.info(f"=== LLM REQUEST ===")
        logger.info(f"Model: {config.ANTHROPIC_MODEL}")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        logger.info(f"Messages count: {len(api_messages)}")
        for i, msg in enumerate(api_messages[-5:]):  # Last 5 messages
            logger.info(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.anthropic_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                result = data["content"][0]["text"]
                logger.info(f"=== LLM RESPONSE ===")
                logger.info(f"Response: {result[:200]}...")
                return result
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            logger.error(f"Response status: {response.status_code if 'response' in dir() else 'N/A'}")
            logger.error(f"Response body: {response.text[:500] if 'response' in dir() else 'N/A'}")
            return "hmm sorry my phone glitched, what were u saying?"
    
    async def _call_openrouter(self, system_prompt: str, messages: List[Dict]) -> str:
        """Call OpenRouter API for NSFW content"""
        
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
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.openrouter_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            return "mm my signal is bad rn, one sec"
    
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
