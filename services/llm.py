"""Client LLM (Anthropic Claude)."""
import logging
import httpx
from pathlib import Path
from settings import ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS
from services.memory import format_memory_for_prompt

logger = logging.getLogger(__name__)

# Charger le system prompt de base
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "luna.txt"
BASE_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


async def generate_response(
    user_message: str,
    history: list[dict],
    memory: dict | None = None
) -> str:
    """
    Génère une réponse Luna avec mémoire.

    Args:
        user_message: Dernier message de l'utilisateur
        history: Historique [{"role": "user/assistant", "content": "..."}]
        memory: Mémoire extraite de l'utilisateur

    Returns:
        Réponse de Luna
    """
    # Construire le system prompt avec mémoire
    if memory:
        memory_text = format_memory_for_prompt(memory)
        system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n## CE QUE TU SAIS SUR LUI:\n{memory_text}"
    else:
        system_prompt = BASE_SYSTEM_PROMPT

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
