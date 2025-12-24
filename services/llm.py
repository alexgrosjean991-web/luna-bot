"""Client LLM multi-provider (Anthropic + OpenRouter) avec contexte mood/phase/story/peaks."""
import re
import asyncio
import random
import logging
import httpx
from pathlib import Path
from settings import (
    ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS, ANTHROPIC_API_VERSION,
    OPENROUTER_API_KEY, OPENROUTER_URL, MAX_TOKENS_PREMIUM
)

# ============== Retry configuration ==============
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Backoff exponentiel en secondes

logger = logging.getLogger(__name__)


def clean_response(text: str) -> str:
    """Supprime les astérisques d'action (*rit*, *sourit*, etc.) de la réponse."""
    # Pattern pour matcher *texte* (actions entre astérisques)
    cleaned = re.sub(r'\*[^*]+\*', '', text)
    # Nettoyer les espaces multiples et les sauts de ligne en trop
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    return cleaned.strip()


# Charger les system prompts
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "luna.txt"
PROMPT_NSFW_PATH = Path(__file__).parent.parent / "prompts" / "luna_nsfw.txt"
BASE_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
NSFW_SYSTEM_PROMPT = PROMPT_NSFW_PATH.read_text(encoding="utf-8")

# URL Anthropic
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


async def call_openrouter(
    messages: list[dict],
    system_prompt: str,
    model: str = "anthracite-org/magnum-v4-72b",
    max_tokens: int = 100,
    temperature: float = 0.8
) -> str:
    """
    Appelle l'API OpenRouter pour les modèles premium.
    """
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY non configuré")
        return random.choice(NATURAL_ERROR_MESSAGES)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://luna-app.com",
        "X-Title": "Luna"
    }

    # Format OpenAI (system message + conversation)
    formatted_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages[-10:]:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    payload = {
        "model": model,
        "messages": formatted_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "frequency_penalty": 0.3,  # Évite répétitions
        "presence_penalty": 0.2,   # Encourage nouveauté
    }

    # Debug: log ce qu'on envoie
    logger.info(f"OpenRouter request: model={model}, max_tokens={max_tokens}, temp={temperature}")
    logger.info(f"System prompt length: {len(system_prompt)} chars")
    logger.info(f"Messages count: {len(formatted_messages)}")

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                raw_text = data["choices"][0]["message"]["content"]
                return clean_response(raw_text)

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"OpenRouter timeout (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                last_error = e
                logger.warning(f"OpenRouter rate limited (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt] * 2)
            elif 400 <= status < 500:
                logger.error(f"OpenRouter client error {status}: {e}")
                return random.choice(NATURAL_ERROR_MESSAGES)
            else:
                last_error = e
                logger.warning(f"OpenRouter server error {status} (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        except Exception as e:
            last_error = e
            logger.error(f"OpenRouter unexpected error: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

    logger.error(f"OpenRouter failed after {MAX_RETRIES} attempts: {last_error}")
    return random.choice(NATURAL_EXIT_MESSAGES)


# ============== V3: Graceful Degradation ==============

# Soft sensual prompt for Haiku fallback (suggestive but not explicit)
SOFT_SENSUAL_INSTRUCTION = """

## INSTRUCTION SPÉCIALE (Fallback)
Tu peux être sensuelle et suggestive. Décris les sensations et émotions
sans être graphiquement explicite. Reste dans l'implicite et le ressenti.
Exemples: "j'ai chaud rien qu'en y pensant", "tu me fais un effet..."
"""

# Natural exit messages when all LLMs fail
NATURAL_EXIT_MESSAGES = [
    "mmh... je suis un peu fatiguée là... on reprend demain ? 😴💕",
    "désolée je déconnecte un peu... t'es toujours là demain ? 💕",
    "j'ai la tête ailleurs ce soir... on se retrouve demain ? 🙈",
    "pardon, je suis un peu à côté de la plaque... demain ? 💕",
]

# Natural error messages (maintains immersion, never technical terms)
NATURAL_ERROR_MESSAGES = [
    "attends j'ai pas capté 🙈",
    "hein ? j'étais ailleurs désolée",
    "pardon j'ai décroché 2 sec",
    "oups j'ai pas suivi 😅",
]


async def call_anthropic_direct(
    messages: list[dict],
    system_prompt: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float = 0.8
) -> str:
    """Direct Anthropic API call for fallback."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": messages[-20:]
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return clean_response(data["content"][0]["text"])
    except Exception as e:
        logger.error(f"Anthropic fallback failed: {e}")
        raise


async def call_with_graceful_fallback(
    messages: list[dict],
    system_prompt: str,
    provider: str,
    model: str,
    tier: int,
    max_tokens: int = MAX_TOKENS_PREMIUM,
    temperature: float = 0.65
) -> str:
    """
    Call LLM with graceful degradation fallback chain.

    Fallback chain:
    1. Primary call (Magnum or Haiku based on tier)
    2. If Magnum fails: Haiku + soft sensual prompt
    3. If all fail: Natural Luna exit message
    """
    # Primary call
    try:
        if provider == "openrouter":
            return await call_openrouter(messages, system_prompt, model, max_tokens, temperature)
        else:
            return await call_anthropic_direct(messages, system_prompt, MAX_TOKENS)
    except Exception as e:
        logger.warning(f"Primary LLM call failed: {e}")

    # Fallback 1: If was Magnum, try Haiku with soft prompt
    if provider == "openrouter" and tier >= 2:
        logger.info("Fallback: Trying Haiku with soft sensual prompt")
        try:
            soft_prompt = system_prompt + SOFT_SENSUAL_INSTRUCTION
            return await call_anthropic_direct(messages, soft_prompt, MAX_TOKENS)
        except Exception as e:
            logger.warning(f"Haiku fallback failed: {e}")

    # Fallback 2: Natural exit message
    logger.error("All LLM calls failed, using natural exit")
    return random.choice(NATURAL_EXIT_MESSAGES)
