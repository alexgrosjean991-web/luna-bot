"""
Memory System - Unified Extraction V2

UN SEUL appel LLM pour tout extraire:
- user_fact: info sur l'utilisateur
- luna_statement: révélation de Luna
- emotional_event: moment émotionnel
- inside_joke: blague partagée
- calendar_date: date/événement à retenir
- user_pattern: pattern comportemental

Chaque extraction a un score d'importance 1-10.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx

from .crud import (
    get_pool,
    get_user_by_id,
    update_user,
    add_event,
    find_similar_event,
    add_inside_joke_v2,
    add_calendar_date,
    update_user_patterns,
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
# UNIFIED EXTRACTION PROMPT
# =============================================================================

UNIFIED_EXTRACTION_PROMPT = """Tu extrais les informations mémorables de cette conversation.

⚠️ DÉTAILS DE LUNA (LE BOT) À NE PAS CONFONDRE:
- Luna, 24 ans, graphiste freelance, Paris
- Pixel (son chat roux)
- Café Oberkampf, appartement Paris
- Parents divorcés, père distant
- Ex Théo, anxiété, insomnies
→ Quand Luna parle de ça, c'est luna_statement, PAS user_fact!

MESSAGE UTILISATEUR:
{user_message}

RÉPONSE LUNA:
{luna_response}

HISTORIQUE RÉCENT:
{history}

JSON strict - retourne UNIQUEMENT ce qui est NOUVEAU et SIGNIFICATIF:
{{
    "user_fact": {{
        "type": "name|age|job|location|like|dislike|secret|family|null",
        "value": "la valeur extraite ou null",
        "importance": 1-10
    }},
    "luna_statement": {{
        "revealed": "révélation personnelle de Luna ou null",
        "topic": "famille|ex|peur|travail|secret|null",
        "importance": 1-10
    }},
    "emotional_event": {{
        "summary": "événement émotionnel ou null",
        "type": "moment|conflict|milestone|null",
        "importance": 1-10
    }},
    "inside_joke": {{
        "trigger": "mot/phrase déclencheur ou null",
        "context": "pourquoi c'est drôle ou null",
        "importance": 1-10
    }},
    "calendar_date": {{
        "date": "YYYY-MM-DD ou null",
        "event": "description ou null",
        "type": "anniversary|promise|plan|birthday|null",
        "importance": 1-10
    }},
    "user_pattern": {{
        "pattern_type": "active_hours|mood_trigger|communication_style|null",
        "value": "la valeur détectée ou null"
    }}
}}

RÈGLES D'IMPORTANCE:
- 9-10: Premier "je t'aime", conflit majeur, secret profond
- 7-8: Révélation personnelle, promesse, moment fort
- 5-6: Info utile, préférence importante
- 3-4: Détail mineur mais mémorable
- 1-2: Trivial, à ignorer

❌ Retourne null/1 pour:
- Réactions banales ("mdr", "ok", "cool")
- Questions sans révélation
- Répétitions d'infos déjà connues
- Phrases génériques

✅ Retourne des valeurs pour:
- Nouvelles infos factuelles (prénom, métier, etc.)
- Révélations émotionnelles
- Moments partagés uniques
- Promesses ou plans futurs
- Blagues récurrentes
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


def _extract_keywords(text: str) -> list[str]:
    """Extrait des keywords basiques d'un texte."""
    stopwords = {
        "dans", "pour", "avec", "cette", "cette", "leur", "mais", "plus",
        "tout", "être", "avoir", "fait", "comme", "aussi", "même", "très",
        "bien", "peut", "quand", "alors", "donc", "encore", "toujours"
    }

    words = re.findall(r'\b[a-zéèêëàâäùûüôöîïç]{4,}\b', text.lower())
    keywords = [w for w in words if w not in stopwords]

    from collections import Counter
    return [w for w, _ in Counter(keywords).most_common(5)]


# =============================================================================
# UNIFIED EXTRACTION FUNCTION
# =============================================================================

async def extract_unified(
    user_id: UUID,
    user_message: str,
    luna_response: str,
    history: list[dict],
    min_importance: int = 3
) -> dict:
    """
    Extraction unifiée - UN SEUL appel LLM pour tout.

    Args:
        user_id: UUID de l'utilisateur
        user_message: Message de l'utilisateur
        luna_response: Réponse de Luna
        history: Historique récent des messages
        min_importance: Score minimum pour stocker (défaut: 3)

    Returns:
        {
            "extracted": dict,      # Tout ce qui a été extrait
            "stored": dict,         # Ce qui a été stocké en DB
            "skipped": list,        # Ce qui a été ignoré (doublons, importance faible)
        }
    """
    if not OPENROUTER_API_KEY:
        logger.error("API key not set for extraction")
        return {"extracted": {}, "stored": {}, "skipped": []}

    # Skip si messages trop courts
    if len(user_message) < 10 and len(luna_response) < 30:
        return {"extracted": {}, "stored": {}, "skipped": ["messages_too_short"]}

    # Formater l'historique
    history_text = "\n".join([
        f"USER: {m.get('content', '')[:100]}" if m.get('role') == 'user'
        else f"LUNA: {m.get('content', '')[:100]}"
        for m in history[-5:]
    ]) or "(pas d'historique)"

    # Appel LLM unifié
    prompt = UNIFIED_EXTRACTION_PROMPT.format(
        user_message=user_message[:500],
        luna_response=luna_response[:500],
        history=history_text
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
                    "max_tokens": 600,
                    "temperature": 0,
                }
            )

            data = response.json()

            if "choices" not in data:
                logger.warning(f"OpenRouter error: {data.get('error', data)}")
                return {"extracted": {}, "stored": {}, "skipped": []}

            content = data["choices"][0]["message"]["content"]
            extracted = _safe_parse_json(content)

            if not extracted:
                logger.warning(f"No JSON found in extraction: {content[:100]}")
                return {"extracted": {}, "stored": {}, "skipped": []}

    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return {"extracted": {}, "stored": {}, "skipped": []}

    # Process and store each extracted item
    stored = {}
    skipped = []

    # Get current user for dedup
    current_user = await get_user_by_id(user_id)
    if not current_user:
        return {"extracted": extracted, "stored": {}, "skipped": ["user_not_found"]}

    # --- USER FACT ---
    user_fact = extracted.get("user_fact", {})
    if user_fact.get("value") and user_fact.get("importance", 0) >= min_importance:
        fact_stored = await _store_user_fact(user_id, user_fact, current_user)
        if fact_stored:
            stored["user_fact"] = fact_stored
        else:
            skipped.append(f"user_fact: duplicate or invalid")

    # --- LUNA STATEMENT ---
    luna_stmt = extracted.get("luna_statement", {})
    if luna_stmt.get("revealed") and luna_stmt.get("importance", 0) >= min_importance:
        stmt_stored = await _store_luna_statement(user_id, luna_stmt)
        if stmt_stored:
            stored["luna_statement"] = stmt_stored
        else:
            skipped.append(f"luna_statement: duplicate")

    # --- EMOTIONAL EVENT ---
    event = extracted.get("emotional_event", {})
    if event.get("summary") and event.get("importance", 0) >= min_importance:
        event_stored = await _store_emotional_event(user_id, event)
        if event_stored:
            stored["emotional_event"] = event_stored
        else:
            skipped.append(f"emotional_event: duplicate or contradiction")

    # --- INSIDE JOKE ---
    joke = extracted.get("inside_joke", {})
    if joke.get("trigger") and joke.get("importance", 0) >= min_importance:
        joke_stored = await _store_inside_joke(user_id, joke)
        if joke_stored:
            stored["inside_joke"] = joke_stored

    # --- CALENDAR DATE ---
    cal_date = extracted.get("calendar_date", {})
    if cal_date.get("date") and cal_date.get("importance", 0) >= min_importance:
        date_stored = await _store_calendar_date(user_id, cal_date)
        if date_stored:
            stored["calendar_date"] = date_stored

    # --- USER PATTERN ---
    pattern = extracted.get("user_pattern", {})
    if pattern.get("pattern_type") and pattern.get("value"):
        await _update_user_pattern(user_id, pattern)
        stored["user_pattern"] = pattern

    if stored:
        logger.info(f"Unified extraction stored: {list(stored.keys())}")

    return {
        "extracted": extracted,
        "stored": stored,
        "skipped": skipped
    }


# =============================================================================
# STORAGE HELPERS
# =============================================================================

async def _store_user_fact(user_id: UUID, fact: dict, current_user: dict) -> Optional[dict]:
    """Store a user fact after dedup."""
    fact_type = fact.get("type")
    value = fact.get("value")

    if not fact_type or not value:
        return None

    updates = {}

    # Simple fields
    if fact_type in ["name", "age", "job", "location"]:
        if value != current_user.get(fact_type):
            updates[fact_type] = value
        else:
            return None  # Duplicate

    # List fields
    elif fact_type in ["like", "dislike", "secret"]:
        field = f"{fact_type}s"  # like -> likes
        existing = current_user.get(field, []) or []
        existing_lower = [str(v).lower() for v in existing]

        if str(value).lower() not in existing_lower:
            updates[field] = [value]  # Append mode in update_user
        else:
            return None  # Duplicate

    # Family dict
    elif fact_type == "family":
        existing_family = current_user.get("family", {}) or {}
        # Value should be "relation: member" format
        if ":" in str(value):
            relation, member = str(value).split(":", 1)
            if relation.strip() not in existing_family:
                updates["family"] = {relation.strip(): member.strip()}
            else:
                return None  # Duplicate

    if updates:
        await update_user(user_id, updates)
        return {"type": fact_type, "value": value, "importance": fact.get("importance", 5)}

    return None


async def _store_luna_statement(user_id: UUID, stmt: dict) -> Optional[dict]:
    """Store a Luna revelation after dedup."""
    revealed = stmt.get("revealed")
    keywords = _extract_keywords(revealed)

    # Check for duplicates
    existing = await find_similar_event(user_id, keywords, "luna_said")
    if existing:
        return None

    importance = stmt.get("importance", 7)
    await add_event(
        user_id=user_id,
        event_type="luna_said",
        summary=revealed,
        keywords=keywords,
        score=importance
    )

    return {"revealed": revealed, "topic": stmt.get("topic"), "importance": importance}


async def _store_emotional_event(user_id: UUID, event: dict) -> Optional[dict]:
    """Store an emotional event after contradiction check."""
    summary = event.get("summary")
    event_type = event.get("type", "moment")
    keywords = _extract_keywords(summary)

    # Check contradiction
    contradiction = await check_user_contradiction(user_id, summary, keywords)

    if contradiction["action"] == "store":
        importance = event.get("importance", 7)
        await add_event(
            user_id=user_id,
            event_type=event_type,
            summary=summary,
            keywords=keywords,
            score=importance
        )
        return {"summary": summary, "type": event_type, "importance": importance}

    elif contradiction["action"] == "update":
        return {"summary": summary, "type": event_type, "updated": True}

    return None


async def _store_inside_joke(user_id: UUID, joke: dict) -> Optional[dict]:
    """Store an inside joke using V2 format."""
    trigger = joke.get("trigger")
    context = joke.get("context", "")
    importance = joke.get("importance", 5)

    await add_inside_joke_v2(
        user_id=user_id,
        trigger=trigger,
        context=context,
        importance=importance
    )

    return {"trigger": trigger, "context": context, "importance": importance}


async def _store_calendar_date(user_id: UUID, cal_date: dict) -> Optional[dict]:
    """Store a calendar date."""
    date_str = cal_date.get("date")
    event_desc = cal_date.get("event")
    event_type = cal_date.get("type", "plan")
    importance = cal_date.get("importance", 5)

    # Validate date format
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"Invalid date format: {date_str}")
        return None

    await add_calendar_date(
        user_id=user_id,
        date=date_str,
        event=event_desc,
        date_type=event_type,
        importance=importance
    )

    return {"date": date_str, "event": event_desc, "type": event_type, "importance": importance}


async def _update_user_pattern(user_id: UUID, pattern: dict) -> None:
    """Update user pattern detection."""
    pattern_type = pattern.get("pattern_type")
    value = pattern.get("value")

    if pattern_type == "active_hours":
        # Value should be like "20-23" or "21"
        try:
            if "-" in str(value):
                start, end = map(int, str(value).split("-"))
                hours = list(range(start, end + 1))
            else:
                hours = [int(value)]
            await update_user_patterns(user_id, "active_hours", hours)
        except ValueError:
            pass

    elif pattern_type == "mood_trigger":
        await update_user_patterns(user_id, "mood_triggers", [value])

    elif pattern_type == "communication_style":
        await update_user_patterns(user_id, "communication_style", value)


# =============================================================================
# LEGACY COMPATIBILITY WRAPPERS
# =============================================================================

async def extract_user_facts(
    user_id: UUID,
    message: str,
    history: list[dict]
) -> dict:
    """
    Legacy wrapper - calls unified extraction.
    Kept for backward compatibility with luna_simple.py.
    """
    # We need a luna_response, but for legacy calls we don't have it
    # Just extract from user message only
    return await extract_unified(
        user_id=user_id,
        user_message=message,
        luna_response="",
        history=history
    )


async def extract_luna_said(
    user_id: UUID,
    luna_response: str,
    user_message: str
) -> Optional[dict]:
    """
    Legacy wrapper - calls unified extraction.
    Kept for backward compatibility with luna_simple.py.
    """
    result = await extract_unified(
        user_id=user_id,
        user_message=user_message,
        luna_response=luna_response,
        history=[]
    )

    # Return in legacy format
    if "luna_statement" in result.get("stored", {}):
        stmt = result["stored"]["luna_statement"]
        return {
            "revealed": stmt.get("revealed"),
            "topic": stmt.get("topic"),
            "keywords": _extract_keywords(stmt.get("revealed", ""))
        }
    return None


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
    Utilise l'extraction unifiée pour chaque paire user/assistant.

    Returns:
        {
            "total_processed": int,
            "facts_found": int,
            "events_found": int,
            "jokes_found": int
        }
    """
    stats = {
        "total_processed": 0,
        "facts_found": 0,
        "events_found": 0,
        "jokes_found": 0
    }

    i = 0
    while i < len(messages):
        user_msg = ""
        luna_msg = ""

        # Get user message
        if messages[i].get("role") == "user":
            user_msg = messages[i]["content"]
            i += 1

        # Get following Luna response
        if i < len(messages) and messages[i].get("role") == "assistant":
            luna_msg = messages[i]["content"]
            i += 1

        # Extract from pair
        if user_msg or luna_msg:
            history = messages[max(0, i-6):i-2]  # Previous context
            result = await extract_unified(
                user_id=user_id,
                user_message=user_msg,
                luna_response=luna_msg,
                history=history
            )

            stored = result.get("stored", {})
            if "user_fact" in stored:
                stats["facts_found"] += 1
            if "emotional_event" in stored or "luna_statement" in stored:
                stats["events_found"] += 1
            if "inside_joke" in stored:
                stats["jokes_found"] += 1

            stats["total_processed"] += 1

    logger.info(f"History extraction complete: {stats}")
    return stats
