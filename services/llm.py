"""Client LLM (Anthropic Claude)."""
import logging
import httpx
from pathlib import Path
from settings import ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS

logger = logging.getLogger(__name__)

# Charger le system prompt
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "luna.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


async def generate_response(
    user_message: str,
    history: list[dict],
    memory: dict | None = None  # Phase 2
) -> str:
    """
    Génère une réponse Luna.

    Args:
        user_message: Dernier message de l'utilisateur
        history: Historique [{"role": "user/assistant", "content": "..."}]
        memory: Mémoire extraite (Phase 2, ignoré pour l'instant)

    Returns:
        Réponse de Luna
    """

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
        "system": SYSTEM_PROMPT,
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
