"""Client LLM (Anthropic Claude) avec contexte mood/phase."""
import logging
import httpx
from pathlib import Path
from settings import ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS
from services.memory import format_memory_for_prompt
from services.relationship import get_phase_instructions, get_phase_temperature
from services.mood import get_mood_instructions, get_mood_context

logger = logging.getLogger(__name__)

# Charger le system prompt de base
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "luna.txt"
BASE_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


async def generate_response(
    user_message: str,
    history: list[dict],
    memory: dict | None = None,
    phase: str = "discovery",
    day_count: int = 1,
    mood: str = "chill"
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

    Returns:
        Réponse de Luna
    """
    # 1. Construire le system prompt
    system_parts = [BASE_SYSTEM_PROMPT]

    # 2. Ajouter la mémoire
    if memory:
        memory_text = format_memory_for_prompt(memory)
        system_parts.append(f"\n## CE QUE TU SAIS SUR LUI:\n{memory_text}")

    # 3. Ajouter les instructions de phase
    phase_instructions = get_phase_instructions(phase, day_count)
    system_parts.append(phase_instructions)

    # 4. Ajouter le contexte d'humeur
    mood_instructions = get_mood_instructions(mood)
    mood_context = get_mood_context(mood)
    system_parts.append(f"\n## TON HUMEUR ACTUELLE:\n{mood_instructions}\nContexte: {mood_context}")

    system_prompt = "\n".join(system_parts)

    # 5. Température selon la phase
    temperature = get_phase_temperature(phase)

    # Construire les messages (historique + message actuel)
    messages = history.copy()
    messages.append({"role": "user", "content": user_message})

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
        "system": system_prompt,
        "messages": messages[-20:]  # Derniers 20 messages
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Erreur LLM: {e}")
        return "dsl j'ai bugé 😅"
