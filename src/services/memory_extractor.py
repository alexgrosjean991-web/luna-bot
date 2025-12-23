"""
Memory Extractor - Sonnet Async
Extrait les faits importants après chaque conversation.
Fire-and-forget pour ne pas bloquer les réponses.
"""

import asyncio
import httpx
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone
from config.settings import config

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyse cette conversation et extrait les informations importantes sur l'utilisateur.

CONVERSATION:
{conversation}

Extrait en JSON (sois CONCIS, max 5 items):
{{
  "facts": ["fait permanent: job, âge, ville, etc"],
  "preferences": ["ce qu'il aime/déteste"],
  "emotions": ["son état émotionnel aujourd'hui"],
  "events": ["événements à venir ou passés importants"],
  "relationship": ["comment il traite Luna, red flags, green flags"]
}}

RÈGLES:
- Seulement les NOUVELLES infos (pas ce qu'on sait déjà)
- Format court: "travaille chez Google", pas de phrases longues
- Si rien de nouveau, retourne des listes vides
- Max 2-3 items par catégorie

JSON:"""


class MemoryExtractor:
    """
    Extrait les mémoires via Sonnet de manière asynchrone.
    Ne bloque jamais le flow principal.
    """

    def __init__(self, db):
        self.db = db
        self.anthropic_url = "https://api.anthropic.com/v1/messages"
        self._pending_extractions: Dict[int, asyncio.Task] = {}

    async def extract_async(self, user_id: int, conversation: List[Dict]) -> None:
        """
        Lance l'extraction en background.
        Fire-and-forget - ne bloque pas.
        """
        # Cancel previous extraction if still running
        if user_id in self._pending_extractions:
            task = self._pending_extractions[user_id]
            if not task.done():
                task.cancel()

        # Start new extraction
        task = asyncio.create_task(self._do_extraction(user_id, conversation))
        self._pending_extractions[user_id] = task

    async def _do_extraction(self, user_id: int, conversation: List[Dict]) -> None:
        """Effectue l'extraction réelle"""
        try:
            # Format conversation
            conv_text = self._format_conversation(conversation[-10:])  # Last 10 msgs
            if len(conv_text) < 50:
                return  # Too short, nothing to extract

            # Call Sonnet
            extracted = await self._call_sonnet(conv_text)
            if not extracted:
                return

            # Store memories
            await self._store_memories(user_id, extracted)

            logger.info(f"Memory extraction complete for user {user_id}")

        except asyncio.CancelledError:
            logger.debug(f"Extraction cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")

    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format messages for extraction"""
        lines = []
        for msg in messages:
            role = "User" if msg.get('role') == 'user' else "Luna"
            content = msg.get('content', '')[:200]  # Truncate long msgs
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _call_sonnet(self, conversation: str) -> Optional[Dict]:
        """Call Sonnet for extraction"""
        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 500,
            "messages": [
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(conversation=conversation)
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.anthropic_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                result = data["content"][0]["text"]

                # Parse JSON
                # Handle potential markdown code blocks
                if "```" in result:
                    result = result.split("```")[1]
                    if result.startswith("json"):
                        result = result[4:]

                return json.loads(result.strip())

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Sonnet API error: {e}")
            return None

    async def _store_memories(self, user_id: int, extracted: Dict) -> None:
        """Store extracted memories in DB"""

        # Facts → Long-term
        for fact in extracted.get("facts", []):
            if fact and len(fact) > 3:
                await self.db.store_memory(
                    user_id=user_id,
                    content=fact,
                    tier="long",
                    memory_type="fact",
                    importance=8.0
                )

        # Preferences → Long-term
        for pref in extracted.get("preferences", []):
            if pref and len(pref) > 3:
                await self.db.store_memory(
                    user_id=user_id,
                    content=pref,
                    tier="long",
                    memory_type="preference",
                    importance=7.0
                )

        # Emotions → Short-term (today only)
        for emotion in extracted.get("emotions", []):
            if emotion and len(emotion) > 3:
                await self.db.store_memory(
                    user_id=user_id,
                    content=f"[{datetime.now().strftime('%d/%m')}] {emotion}",
                    tier="short",
                    memory_type="emotion",
                    importance=5.0
                )

        # Events → Mid-term
        for event in extracted.get("events", []):
            if event and len(event) > 3:
                await self.db.store_memory(
                    user_id=user_id,
                    content=event,
                    tier="mid",
                    memory_type="event",
                    importance=7.0
                )

        # Relationship notes → Long-term
        for rel in extracted.get("relationship", []):
            if rel and len(rel) > 3:
                await self.db.store_memory(
                    user_id=user_id,
                    content=rel,
                    tier="long",
                    memory_type="relationship",
                    importance=9.0
                )


# Singleton
_extractor: Optional[MemoryExtractor] = None


def get_memory_extractor(db) -> MemoryExtractor:
    global _extractor
    if _extractor is None:
        _extractor = MemoryExtractor(db)
    return _extractor
