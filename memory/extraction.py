"""
Memory System - Fact Extraction

Utilise Haiku pour extraire les faits des messages.
Avec déduplication pour éviter les doublons.
"""

import json
import logging
import re
from typing import Optional
from uuid import UUID

import httpx

from .crud import (
    get_pool,
    get_user_by_id,
    update_user,
    add_event,
    find_similar_event,
)
from .coherence import check_user_contradiction

logger = logging.getLogger(__name__)

# Config
OPENROUTER_API_KEY = None  # Injecté au démarrage
HAIKU_MODEL = "anthropic/claude-3-haiku"


def set_api_key(key: str):
    """Injecte la clé API."""
    global OPENROUTER_API_KEY
    OPENROUTER_API_KEY = key


# =============================================================================
# EXTRACTION PROMPTS
# =============================================================================

EXTRACT_USER_FACTS_PROMPT = """Tu extrais UNIQUEMENT les infos que L'UTILISATEUR dit sur LUI-MÊME.

⚠️ DÉTAILS DE LUNA (LE BOT) À IGNORER ABSOLUMENT:
- Luna, 24 ans, graphiste freelance, Paris
- Pixel (son chat roux)
- Café Oberkampf, appartement Paris
- Parents divorcés, père distant
- Ex Théo, anxiété, insomnies
- Fille unique
→ Si tu vois ces éléments, c'est LUNA qui parle d'elle, PAS l'utilisateur!

MESSAGE DE L'UTILISATEUR:
{message}

HISTORIQUE (UTILISATEUR vs [LUNA/BOT]):
{history}

JSON strict:
{{
    "name": "prénom que l'UTILISATEUR donne pour LUI-MÊME ou null",
    "age": "âge que l'UTILISATEUR dit avoir ou null",
    "job": "métier que l'UTILISATEUR dit faire ou null",
    "location": "où l'UTILISATEUR dit habiter ou null",
    "likes": ["ce que l'UTILISATEUR dit aimer"],
    "dislikes": ["ce que l'UTILISATEUR dit ne pas aimer"],
    "family": {{"relation": "membre de la famille de l'UTILISATEUR"}},
    "secrets": ["confidences personnelles de l'UTILISATEUR"],
    "moment": "événement vécu par l'UTILISATEUR ou null"
}}

RÈGLES:
- UNIQUEMENT ce que l'UTILISATEUR dit sur LUI-MÊME
- Les messages [LUNA/BOT] = IGNORER TOTALEMENT
- "Pixel", "Oberkampf", "graphiste", "Paris" = détails de Luna → IGNORER
- Si pas dit explicitement par l'utilisateur → null ou []
"""

EXTRACT_LUNA_SAID_PROMPT = """Extrais UNIQUEMENT les RÉVÉLATIONS PERSONNELLES de Luna sur sa vie.

RÉPONSE DE LUNA:
{response}

CONTEXTE:
{context}

Une révélation = Luna partage quelque chose de PERSONNEL sur:
- Sa famille (parents, ex)
- Ses émotions/peurs
- Son passé/souvenirs
- Ses secrets

JSON strict:
{{
    "revealed": "la révélation personnelle ou null",
    "topic": "famille/ex/peur/travail/secret ou null",
    "keywords": ["mots-clés"]
}}

❌ NE PAS EXTRAIRE (retourner null):
- Réponses factuelles ("il est 23h", "je suis sûre")
- Réactions ("mdr", "ah cool", "ok")
- Questions de Luna
- Phrases génériques ("je suis là", "pas grand chose")
- Descriptions d'actions ("je te suis en PV")

✅ EXTRAIRE SEULEMENT:
- "mes parents sont divorcés" → révélation famille
- "mon ex m'a fait du mal" → révélation ex
- "j'ai peur d'être abandonnée" → révélation peur
- "je fais de l'anxiété" → révélation personnel
"""


# =============================================================================
# JSON PARSING HELPER
# =============================================================================

def _safe_parse_json(content: str) -> Optional[dict]:
    """
    Parse JSON de manière robuste.
    Gère les blocs markdown, les multiples objets, et les erreurs.
    """
    if not content:
        return None

    # Nettoyer le contenu (enlever markdown code blocks)
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)

    # Trouver le premier objet JSON complet
    # On utilise une approche par comptage de braces
    start = content.find('{')
    if start == -1:
        return None

    brace_count = 0
    end = start
    for i, char in enumerate(content[start:], start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

    if brace_count != 0:
        return None

    json_str = content[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

async def extract_user_facts(
    user_id: UUID,
    message: str,
    history: list[dict]
) -> dict:
    """
    Extrait les faits user d'un message via Haiku.

    Returns:
        {
            "extracted": dict,  # Facts bruts extraits
            "stored": dict,     # Ce qui a été stocké (après dedup)
            "skipped": list,    # Ce qui a été ignoré (doublons)
        }
    """
    if not OPENROUTER_API_KEY:
        logger.error("API key not set for extraction")
        return {"extracted": {}, "stored": {}, "skipped": []}

    # Formater l'historique (être TRÈS explicite sur qui parle)
    history_text = "\n".join([
        f"UTILISATEUR: {m.get('content', '')[:100]}" if m.get('role') == 'user'
        else f"[LUNA/BOT - IGNORER]: {m.get('content', '')[:100]}"
        for m in history[-5:]
    ])

    # Appel Haiku
    prompt = EXTRACT_USER_FACTS_PROMPT.format(
        message=message,
        history=history_text or "(pas d'historique)"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HAIKU_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0,
                }
            )

            data = response.json()

            # Check for API errors
            if "choices" not in data:
                logger.warning(f"OpenRouter error (no choices): {data.get('error', data)}")
                return {"extracted": {}, "stored": {}, "skipped": []}

            content = data["choices"][0]["message"]["content"]

            # Parser JSON - utiliser une méthode plus robuste
            extracted = _safe_parse_json(content)
            if not extracted:
                logger.warning(f"No JSON found in extraction response: {content[:100]}")
                return {"extracted": {}, "stored": {}, "skipped": []}

    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return {"extracted": {}, "stored": {}, "skipped": []}

    # Déduplication et stockage
    stored = {}
    skipped = []

    # Récupérer les faits actuels pour comparer
    current_user = await get_user_by_id(user_id)
    if not current_user:
        return {"extracted": extracted, "stored": {}, "skipped": []}

    # Traiter chaque fait
    updates = {}

    # Facts simples (name, age, job, location)
    for field in ["name", "age", "job", "location"]:
        new_value = extracted.get(field)
        if new_value and new_value != current_user.get(field):
            updates[field] = new_value
            stored[field] = new_value

    # Lists (likes, dislikes, secrets)
    for field in ["likes", "dislikes", "secrets"]:
        new_values = extracted.get(field, [])
        if new_values:
            existing = current_user.get(field, []) or []
            # Filtrer les doublons (case insensitive)
            existing_lower = [str(v).lower() for v in existing]
            unique_new = [v for v in new_values if str(v).lower() not in existing_lower]

            if unique_new:
                updates[field] = unique_new
                stored[field] = unique_new
            else:
                skipped.extend([f"{field}: {v}" for v in new_values])

    # Family dict
    family = extracted.get("family", {})
    if family:
        existing_family = current_user.get("family", {}) or {}
        new_family = {k: v for k, v in family.items() if k not in existing_family}
        if new_family:
            updates["family"] = new_family
            stored["family"] = new_family

    # Stocker les updates
    if updates:
        await update_user(user_id, updates)
        logger.info(f"Stored user facts: {list(updates.keys())}")

    # Événement "moment" → timeline
    moment = extracted.get("moment")
    if moment:
        # Check contradiction
        keywords = _extract_keywords(moment)
        contradiction = await check_user_contradiction(user_id, moment, keywords)

        if contradiction["action"] == "store":
            await add_event(
                user_id=user_id,
                event_type="moment",
                summary=moment,
                keywords=keywords,
                score=7
            )
            stored["moment"] = moment
            logger.info(f"Stored moment: {moment[:50]}...")
        elif contradiction["action"] == "update":
            # Mettre à jour l'événement existant
            stored["moment"] = f"[updated] {moment}"
        else:
            skipped.append(f"moment: {moment} (contradiction)")

    return {
        "extracted": extracted,
        "stored": stored,
        "skipped": skipped
    }


async def extract_luna_said(
    user_id: UUID,
    luna_response: str,
    user_message: str
) -> Optional[dict]:
    """
    Extrait ce que Luna a révélé sur elle-même.

    Returns:
        {"revealed": str, "topic": str, "keywords": list} or None
    """
    if not OPENROUTER_API_KEY:
        return None

    # Skip si réponse courte (probablement pas de révélation)
    if len(luna_response) < 50:
        return None

    prompt = EXTRACT_LUNA_SAID_PROMPT.format(
        response=luna_response,
        context=user_message[:200]
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HAIKU_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0,
                }
            )

            data = response.json()

            # Check for API errors
            if "choices" not in data:
                logger.warning(f"OpenRouter error (no choices): {data.get('error', data)}")
                return None

            content = data["choices"][0]["message"]["content"]

            # Parser JSON - utiliser une méthode plus robuste
            result = _safe_parse_json(content)
            if not result:
                return None

            if not result.get("revealed"):
                return None

            # Dédup: vérifier si on a déjà ce luna_said
            existing = await find_similar_event(
                user_id,
                result.get("keywords", []),
                "luna_said"
            )

            if existing:
                logger.debug(f"Luna_said already exists: {result['revealed'][:30]}...")
                return None

            # Stocker
            await add_event(
                user_id=user_id,
                event_type="luna_said",
                summary=result["revealed"],
                keywords=result.get("keywords", []),
                score=8  # Important pour cohérence
            )

            logger.info(f"Stored luna_said: {result['revealed'][:50]}...")
            return result

    except Exception as e:
        logger.error(f"Luna_said extraction error: {e}")
        return None


def _extract_keywords(text: str) -> list[str]:
    """Extrait des keywords basiques d'un texte."""
    # Mots importants (> 4 chars, pas de stopwords)
    stopwords = {
        "dans", "pour", "avec", "cette", "cette", "leur", "mais", "plus",
        "tout", "être", "avoir", "fait", "comme", "aussi", "même", "très",
        "bien", "peut", "quand", "alors", "donc", "encore", "toujours"
    }

    words = re.findall(r'\b[a-zéèêëàâäùûüôöîïç]{4,}\b', text.lower())
    keywords = [w for w in words if w not in stopwords]

    # Garder les 5 plus fréquents
    from collections import Counter
    return [w for w, _ in Counter(keywords).most_common(5)]


# =============================================================================
# BATCH PROCESSING (pour historique)
# =============================================================================

async def extract_from_history(
    user_id: UUID,
    messages: list[dict],
    batch_size: int = 10
) -> dict:
    """
    Extrait les faits d'un historique de messages.
    Utile pour initialiser la mémoire d'un user existant.

    Returns:
        {
            "total_processed": int,
            "facts_found": int,
            "moments_found": int,
            "luna_said_found": int
        }
    """
    stats = {
        "total_processed": 0,
        "facts_found": 0,
        "moments_found": 0,
        "luna_said_found": 0
    }

    for i in range(0, len(messages), batch_size):
        batch = messages[i:i + batch_size]

        for j, msg in enumerate(batch):
            if msg.get("role") == "user":
                # Extraire les faits user
                history = batch[:j]
                result = await extract_user_facts(user_id, msg["content"], history)

                if result["stored"]:
                    stats["facts_found"] += len(result["stored"])
                if "moment" in result.get("stored", {}):
                    stats["moments_found"] += 1

            elif msg.get("role") == "assistant":
                # Extraire ce que Luna a dit
                prev_user_msg = ""
                if j > 0 and batch[j-1].get("role") == "user":
                    prev_user_msg = batch[j-1]["content"]

                luna_said = await extract_luna_said(user_id, msg["content"], prev_user_msg)
                if luna_said:
                    stats["luna_said_found"] += 1

            stats["total_processed"] += 1

    logger.info(f"History extraction complete: {stats}")
    return stats
