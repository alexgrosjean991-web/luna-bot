"""Extraction et injection de mémoire."""
import json
import logging
import httpx
from settings import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extrais UNIQUEMENT les informations sur l'UTILISATEUR (User), PAS sur Luna.

CONTEXTE IMPORTANT:
- Luna est une IA/assistante qui parle d'elle-même (son chat Pixel, son job graphiste, Paris, etc.)
- Tu dois IGNORER tout ce que Luna dit sur ELLE-MÊME
- Tu extrais SEULEMENT ce que l'UTILISATEUR révèle sur LUI

CONVERSATION:
{conversation}

MÉMOIRE ACTUELLE DE L'UTILISATEUR:
{current_memory}

Retourne UNIQUEMENT un JSON avec les infos de L'UTILISATEUR:
{{
    "prenom": "string ou null",
    "age": "number ou null",
    "ville": "string ou null",
    "travail": "string ou null",
    "hobbies": ["liste"],
    "problemes": ["liste"],
    "likes": ["liste"],
    "dislikes": ["liste"],
    "facts": ["faits sur l'utilisateur"],
    "relationship_status": "string ou null",
    "mood_recent": "humeur de l'utilisateur"
}}

RÈGLES CRITIQUES:
- IGNORER: chat Pixel, graphiste freelance, Paris 11ème = c'est LUNA, pas l'utilisateur
- EXTRAIRE: seulement ce que USER dit explicitement sur lui-même
- Ne pas inventer, ne pas confondre Luna avec l'utilisateur
- Retourner UNIQUEMENT le JSON"""


async def extract_memory(
    conversation: list[dict],
    current_memory: dict
) -> dict:
    """
    Extrait les infos importantes de la conversation via LLM.

    Args:
        conversation: Liste des derniers messages
        current_memory: Mémoire actuelle

    Returns:
        Nouvelle mémoire mise à jour
    """
    # Formater la conversation
    conv_text = "\n".join([
        f"{'User' if m['role'] == 'user' else 'Luna'}: {m['content']}"
        for m in conversation[-10:]
    ])

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 500,
        "messages": [{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(
                conversation=conv_text,
                current_memory=json.dumps(current_memory, ensure_ascii=False)
            )
        }]
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
            result_text = data["content"][0]["text"].strip()

            # Nettoyer si wrapped dans ```json
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()

            new_memory = json.loads(result_text)
            logger.info(f"Mémoire extraite: {new_memory}")
            return new_memory

    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON mémoire: {e}")
        return current_memory
    except Exception as e:
        logger.error(f"Erreur extraction mémoire: {e}")
        return current_memory


def format_memory_for_prompt(memory: dict) -> str:
    """Formate la mémoire pour injection dans le system prompt."""
    if not memory:
        return "Tu ne sais encore rien sur lui."

    parts = []

    if memory.get("prenom"):
        parts.append(f"Il s'appelle {memory['prenom']}")
    if memory.get("age"):
        parts.append(f"Il a {memory['age']} ans")
    if memory.get("ville"):
        parts.append(f"Il habite à {memory['ville']}")
    if memory.get("travail"):
        parts.append(f"Il travaille comme {memory['travail']}")
    if memory.get("hobbies"):
        parts.append(f"Ses hobbies: {', '.join(memory['hobbies'])}")
    if memory.get("likes"):
        parts.append(f"Il aime: {', '.join(memory['likes'])}")
    if memory.get("dislikes"):
        parts.append(f"Il n'aime pas: {', '.join(memory['dislikes'])}")
    if memory.get("problemes"):
        parts.append(f"Ses préoccupations: {', '.join(memory['problemes'])}")
    if memory.get("relationship_status"):
        parts.append(f"Situation: {memory['relationship_status']}")
    if memory.get("facts"):
        parts.append(f"Autres: {', '.join(memory['facts'])}")
    if memory.get("mood_recent"):
        parts.append(f"Humeur: {memory['mood_recent']}")

    return ". ".join(parts) + "." if parts else "Tu ne sais encore rien sur lui."
