"""Client LLM multi-provider (Anthropic + OpenRouter) avec contexte mood/phase/story/peaks."""
import re
import asyncio
import logging
import httpx
from pathlib import Path
from settings import (
    ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS, ANTHROPIC_API_VERSION,
    OPENROUTER_API_KEY, OPENROUTER_URL, MAX_TOKENS_PREMIUM
)

# ============== HIGH FIX: Retry configuration ==============
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Backoff exponentiel en secondes
from services.memory import format_memory_for_prompt, get_memory_recall_instruction
from services.relationship import get_phase_instructions, get_phase_temperature
from services.mood import get_mood_instructions, get_mood_context
from services.story_arcs import get_story_instruction
from services.teasing import get_teasing_instruction
from services.emotional_peaks import get_emotional_instruction

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
    model: str = "mistralai/mixtral-8x22b-instruct",
    max_tokens: int = 60,
    temperature: float = 0.75
) -> str:
    """
    Appelle l'API OpenRouter pour les modèles premium.
    """
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY non configuré")
        return "dsl je bug 😅"

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
    }

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
                return "dsl j'ai bugé 😅"
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
    return "dsl je lag un peu 😅"


async def generate_response(
    user_message: str,
    history: list[dict],
    memory: dict | None = None,
    phase: str = "discovery",
    day_count: int = 1,
    mood: str = "chill",
    emotional_state: str | None = None,
    extra_instructions: str | None = None,
    provider: str = "anthropic",
    model_override: str | None = None
) -> str:
    """
    Génère une réponse Luna avec contexte complet.

    Args:
        user_message: Dernier message de l'utilisateur
        history: Historique [{"role": "user/assistant", "content": "..."}]
        memory: Mémoire extraite de l'utilisateur
        phase: Phase de la relation (discovery, connection, close)
        day_count: Numéro du jour
        mood: Humeur actuelle (happy, chill, playful, flirty, tired, busy, emotional)
        emotional_state: État émotionnel si pic en cours (opener, follow_up, resolution)
        extra_instructions: Instructions V5 psychology (affection, inside jokes, etc.)
        provider: "anthropic" ou "openrouter"
        model_override: Modèle spécifique à utiliser (optionnel)

    Returns:
        Réponse de Luna
    """
    # 1. Construire le system prompt (NSFW pour OpenRouter)
    base_prompt = NSFW_SYSTEM_PROMPT if provider == "openrouter" else BASE_SYSTEM_PROMPT
    system_parts = [base_prompt]

    # 2. Ajouter la mémoire
    if memory:
        memory_text = format_memory_for_prompt(memory)
        system_parts.append(f"\n## CE QUE TU SAIS SUR LUI:\n{memory_text}")

        # 2b. Rappel mémoire actif (40% chance)
        memory_recall = get_memory_recall_instruction(memory)
        if memory_recall:
            system_parts.append(memory_recall)

    # 3. Ajouter les instructions de phase
    phase_instructions = get_phase_instructions(phase, day_count)
    system_parts.append(phase_instructions)

    # 4. Ajouter le contexte d'humeur
    mood_instructions = get_mood_instructions(mood)
    mood_context = get_mood_context(mood)
    system_parts.append(f"\n## TON HUMEUR ACTUELLE:\n{mood_instructions}\nContexte: {mood_context}")

    # 5. Ajouter story arc (contexte de vie)
    story_instruction = get_story_instruction(day_count)
    if story_instruction:
        system_parts.append(story_instruction)

    # 6. Ajouter teasing instruction (J2-5)
    teasing_instruction = get_teasing_instruction(day_count)
    if teasing_instruction:
        system_parts.append(teasing_instruction)

    # 7. Ajouter emotional peak instruction (si en cours)
    if emotional_state:
        emotional_instruction = get_emotional_instruction(day_count, emotional_state)
        if emotional_instruction:
            system_parts.append(emotional_instruction)

    # 8. V5: Ajouter extra instructions (psychology modules)
    if extra_instructions:
        system_parts.append(f"\n## INSTRUCTIONS SUPPLÉMENTAIRES:\n{extra_instructions}")

    system_prompt = "\n".join(system_parts)

    # 5. Température selon la phase
    temperature = get_phase_temperature(phase)

    # Construire les messages (historique + message actuel)
    messages = history.copy()
    messages.append({"role": "user", "content": user_message})

    # ============== ROUTER: OpenRouter pour premium ==============
    if provider == "openrouter":
        model = model_override or "mistralai/mixtral-8x22b-instruct"
        logger.info(f"Using OpenRouter ({model})")
        return await call_openrouter(
            messages=messages,
            system_prompt=system_prompt,
            model=model,
            max_tokens=MAX_TOKENS_PREMIUM,
            temperature=0.75
        )

    # ============== Anthropic (default) ==============
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
        "system": system_prompt,
        "messages": messages[-20:]  # Derniers 20 messages
    }

    # ============== HIGH FIX: Retry avec backoff ==============
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                raw_text = data["content"][0]["text"]
                return clean_response(raw_text)

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"LLM timeout (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # Ne pas retry sur erreurs client (4xx) sauf rate limit (429)
            if status == 429:
                last_error = e
                logger.warning(f"LLM rate limited (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt] * 2)  # Plus long pour rate limit
            elif 400 <= status < 500:
                logger.error(f"LLM client error {status}: {e}")
                return "dsl j'ai bugé 😅"
            else:
                last_error = e
                logger.warning(f"LLM server error {status} (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        except Exception as e:
            last_error = e
            logger.error(f"LLM unexpected error: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

    # Toutes les tentatives ont échoué
    logger.error(f"LLM failed after {MAX_RETRIES} attempts: {last_error}")
    return "dsl je lag un peu 😅"
