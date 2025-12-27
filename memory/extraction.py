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

⚠️⚠️⚠️ RÈGLE CRITIQUE - LUNA vs UTILISATEUR ⚠️⚠️⚠️

LUNA (le bot) a ces caractéristiques FIXES - NE JAMAIS LES EXTRAIRE COMME user_fact:
- Luna, 23 ans, UI/UX designer freelance, Paris 11ème
- Pixel (son chat tigré roux)
- Café Oberkampf, appartement Paris
- Parents divorcés, père distant
- Ex toxique (gamer), anxiété, insomnies
- Gym le matin, gaming le soir (Valorant, LoL)

EXEMPLES CONCRETS:

❌ FAUX - Luna dit "je suis graphiste":
  user_fact: {{"type": "job", "value": "graphiste"}}  ← ERREUR! C'est le job de LUNA

✅ CORRECT - Luna dit "je suis graphiste":
  luna_statement: {{"revealed": "je suis graphiste", "topic": "travail"}}

❌ FAUX - Luna dit "j'ai un chat qui s'appelle Pixel":
  user_fact: {{"type": "like", "value": "chats"}}  ← ERREUR! C'est le chat de LUNA

✅ CORRECT - User dit "je m'appelle Lucas, je suis dev à Lyon":
  user_fact: {{"type": "name", "value": "Lucas", "importance": 8}}
  (puis un 2e appel pour job et location, ou tu peux prioriser le plus important)

✅ CORRECT - User dit "j'adore le gaming":
  user_fact: {{"type": "like", "value": "gaming", "importance": 6}}

⛔⛔⛔ RÈGLE ABSOLUE - NOM DE L'UTILISATEUR vs NOMS DE PROCHES ⛔⛔⛔

"type": "name" = UNIQUEMENT le prénom de l'utilisateur LUI-MÊME (importance 8+)
"type": "family" = prénoms de sa famille/amis (importance 6)

EXEMPLES CONCRETS:
- "Je m'appelle Lucas" → {{"type": "name", "value": "Lucas", "importance": 8}} ✅
- "Moi c'est Mika" → {{"type": "name", "value": "Mika", "importance": 8}} ✅
- "Mon frère s'appelle Pierre" → {{"type": "family", "value": "frère: Pierre", "importance": 6}} ✅
- "Ma sœur Luana" → {{"type": "family", "value": "sœur: Luana", "importance": 6}} ✅
- "Mon pote Alex" → {{"type": "family", "value": "ami: Alex", "importance": 6}} ✅

⛔ ERREUR GRAVE: mettre un nom de proche dans "type": "name"
⛔ "Mon frère Patrick" → {{"type": "name", "value": "Patrick"}} ← FAUX!
✅ "Mon frère Patrick" → {{"type": "family", "value": "frère: Patrick"}} ← CORRECT!

MESSAGE UTILISATEUR:
{user_message}

RÉPONSE LUNA:
{luna_response}

HISTORIQUE RÉCENT:
{history}

JSON strict - retourne UNIQUEMENT ce qui est NOUVEAU et SIGNIFICATIF:
{{
    "user_facts": [
        {{"type": "name|age|job|location|like|dislike|secret|family", "value": "...", "importance": 1-10}}
    ],
    "luna_statement": {{
        "revealed": "révélation personnelle de LUNA ou null",
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

⚠️ IMPORTANT: user_facts est un ARRAY - tu peux extraire PLUSIEURS faits à la fois!
Exemple: "Je m'appelle Lucas, je suis dev à Lyon" →
"user_facts": [
    {{"type": "name", "value": "Lucas", "importance": 8}},
    {{"type": "job", "value": "développeur", "importance": 6}},
    {{"type": "location", "value": "Lyon", "importance": 6}}
]
Si rien à extraire: "user_facts": []

RÈGLES D'IMPORTANCE:
- 9-10: Premier "je t'aime", conflit majeur, secret profond
- 7-8: Prénom de l'utilisateur, révélation personnelle, promesse
- 5-6: Job, location, préférence importante
- 3-4: Détail mineur mais mémorable
- 1-2: Trivial, à ignorer

❌ Retourne null/1 pour:
- Infos sur LUNA (graphiste, Pixel, Paris, ex, etc.)
- Réactions banales ("mdr", "ok", "cool")
- Répétitions d'infos déjà connues

✅ Retourne des valeurs pour user_fact UNIQUEMENT si L'UTILISATEUR parle de LUI-MÊME:
- "je m'appelle X" → name
- "je bosse comme X" / "je suis X (métier)" → job
- "j'habite à X" → location
- "j'aime X" / "je kiffe X" → like

⛔⛔⛔ RÈGLE ABSOLUE - ZÉRO HALLUCINATION ⛔⛔⛔
- JAMAIS inventer un prénom si l'utilisateur ne l'a pas dit EXPLICITEMENT
- JAMAIS deviner des informations
- Si le message ne contient PAS "je m'appelle X" ou "moi c'est X" → user_facts: []
- En cas de doute → user_facts: []

EXEMPLES:
❌ "Je vais à la gym" → user_facts: [] (pas de prénom mentionné!)
❌ "Salut ça va?" → user_facts: [] (rien de personnel)
✅ "Je m'appelle Lucas" → user_facts: [{{"type": "name", "value": "Lucas"}}]
✅ "Moi c'est Lucas, dev à Lyon" → user_facts: [{{"type": "name", "value": "Lucas"}}, {{"type": "job", "value": "dev"}}]
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
# VALIDATION HELPERS
# =============================================================================

# Patterns that indicate bad inside jokes (Luna making errors)
BAD_JOKE_PATTERNS = [
    "luna a oublié", "luna oublie", "luna a confondu", "luna confond",
    "luna s'excuse", "luna se trompe", "luna a raté", "erreur de luna",
    "bug de luna", "luna ne se souvient pas", "luna a perdu",
]

# Patterns that indicate bad user patterns (user complaints)
BAD_PATTERN_KEYWORDS = [
    "oublie", "rappelle", "déjà dit", "répète", "mémoire", "souviens",
    "confondu", "erreur", "bug", "problème",
]


def _is_bad_inside_joke(joke: dict) -> bool:
    """Check if an inside joke is about Luna making mistakes."""
    trigger = str(joke.get("trigger", "")).lower()
    context = str(joke.get("context", "")).lower()
    combined = f"{trigger} {context}"

    for pattern in BAD_JOKE_PATTERNS:
        if pattern in combined:
            return True
    return False


def _is_bad_pattern(pattern: dict) -> bool:
    """Check if a user pattern is about complaining."""
    value = str(pattern.get("value", "")).lower()
    pattern_type = str(pattern.get("pattern_type", "")).lower()

    # communication_style patterns mentioning complaints are bad
    if pattern_type == "communication_style":
        for keyword in BAD_PATTERN_KEYWORDS:
            if keyword in value:
                return True
    return False


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

            # Log raw JSON for debugging
            logger.info(f"Extraction raw response: {content[:500]}")

            extracted = _safe_parse_json(content)

            if not extracted:
                logger.warning(f"No JSON found in extraction: {content[:100]}")
                return {"extracted": {}, "stored": {}, "skipped": []}

            # Log parsed extraction
            logger.info(f"Extraction parsed: {json.dumps(extracted, ensure_ascii=False)[:300]}")

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

    # --- USER FACTS (array) ---
    user_facts = extracted.get("user_facts") or []
    # Handle legacy single user_fact format
    if not user_facts and extracted.get("user_fact"):
        user_facts = [extracted.get("user_fact")]

    stored_facts = []
    for fact in user_facts:
        if not isinstance(fact, dict):
            continue

        # ANTI-HALLUCINATION: Vérifier que la valeur apparaît VRAIMENT dans le message
        # S'applique à TOUS les types de facts
        fact_value = str(fact.get("value", "")).lower()
        fact_type = fact.get("type", "")

        if fact_value:
            # Chercher la valeur ou ses mots principaux dans le message
            message_lower = user_message.lower()
            found = False

            # Vérification directe
            if fact_value in message_lower:
                found = True
            else:
                # Pour les valeurs multi-mots, chercher les mots clés (min 3 chars)
                words = [w for w in fact_value.split() if len(w) >= 3]
                if words:
                    # Au moins 50% des mots doivent être présents
                    matches = sum(1 for w in words if w in message_lower)
                    if matches >= len(words) * 0.5:
                        found = True

            if not found:
                logger.warning(f"HALLUCINATION blocked: {fact_type} '{fact.get('value')}' not found in user message")
                skipped.append(f"{fact_type} hallucination: {fact.get('value')}")
                continue

        if fact.get("value") and fact.get("importance", 0) >= min_importance:
            fact_stored = await _store_user_fact(user_id, fact, current_user)
            if fact_stored:
                stored_facts.append(fact_stored)
            else:
                skipped.append(f"user_fact ({fact.get('type')}): duplicate or invalid")

    if stored_facts:
        stored["user_facts"] = stored_facts

    # --- LUNA STATEMENT ---
    luna_stmt = extracted.get("luna_statement") or {}
    if luna_stmt.get("revealed") and luna_stmt.get("importance", 0) >= min_importance:
        stmt_stored = await _store_luna_statement(user_id, luna_stmt)
        if stmt_stored:
            stored["luna_statement"] = stmt_stored
        else:
            skipped.append(f"luna_statement: duplicate")

    # --- EMOTIONAL EVENT ---
    event = extracted.get("emotional_event") or {}
    if event.get("summary") and event.get("importance", 0) >= min_importance:
        event_stored = await _store_emotional_event(user_id, event)
        if event_stored:
            stored["emotional_event"] = event_stored
        else:
            skipped.append(f"emotional_event: duplicate or contradiction")

    # --- INSIDE JOKE (with validation) ---
    joke = extracted.get("inside_joke") or {}
    if joke.get("trigger") and joke.get("importance", 0) >= min_importance:
        # Filter out bad jokes mentioning Luna's mistakes
        if not _is_bad_inside_joke(joke):
            joke_stored = await _store_inside_joke(user_id, joke)
            if joke_stored:
                stored["inside_joke"] = joke_stored
        else:
            skipped.append("inside_joke: filtered (mentions Luna error)")

    # --- CALENDAR DATE ---
    cal_date = extracted.get("calendar_date") or {}
    if cal_date.get("date") and cal_date.get("importance", 0) >= min_importance:
        date_stored = await _store_calendar_date(user_id, cal_date)
        if date_stored:
            stored["calendar_date"] = date_stored

    # --- USER PATTERN (with validation) ---
    pattern = extracted.get("user_pattern") or {}
    if pattern.get("pattern_type") and pattern.get("value"):
        # Filter out bad patterns mentioning user complaints
        if not _is_bad_pattern(pattern):
            await _update_user_pattern(user_id, pattern)
            stored["user_pattern"] = pattern
        else:
            skipped.append("user_pattern: filtered (mentions complaint)")

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

# Mots qui ne sont PAS des prénoms (nationalités, jobs, etc.)
INVALID_NAMES = {
    # Nationalités
    "français", "francais", "française", "francaise", "sénégalais", "senegalais",
    "marocain", "algérien", "algerien", "tunisien", "ivoirien", "camerounais",
    "malien", "guinéen", "guineen", "congolais", "togolais", "béninois", "beninois",
    "américain", "americain", "anglais", "espagnol", "italien", "allemand",
    "portugais", "belge", "suisse", "canadien", "brésilien", "bresilien",
    "africain", "européen", "europeen", "asiatique", "arabe",
    # Jobs communs
    "maçon", "macon", "plombier", "électricien", "electricien", "menuisier",
    "dev", "développeur", "developpeur", "designer", "graphiste", "freelance",
    # Mots génériques
    "mec", "gars", "homme", "femme", "fille", "garçon", "garcon", "type",
    "noir", "blanc", "beur", "rebeu", "renoi", "feuj",
    "chantier", "travail", "boulot", "taf",
}


def _is_valid_name(value: str) -> bool:
    """Vérifie si une valeur ressemble à un vrai prénom."""
    if not value or len(value) < 2 or len(value) > 20:
        return False
    # Rejeter les mots invalides
    if value.lower() in INVALID_NAMES:
        return False
    # Doit commencer par une majuscule (prénom classique)
    if not value[0].isupper():
        return False
    # Pas de chiffres
    if any(c.isdigit() for c in value):
        return False
    return True


async def _store_user_fact(user_id: UUID, fact: dict, current_user: dict) -> Optional[dict]:
    """Store a user fact after dedup."""
    fact_type = fact.get("type")
    value = fact.get("value")

    if not fact_type or not value:
        return None

    updates = {}

    # Simple fields
    if fact_type in ["name", "age", "job", "location"]:
        # Validation spéciale pour les noms
        if fact_type == "name" and not _is_valid_name(str(value)):
            logger.warning(f"Invalid name rejected: '{value}'")
            return None

        # Validation pour les locations (rejeter les mots génériques)
        if fact_type == "location":
            invalid_locations = {"chantier", "travail", "boulot", "maison", "chez moi", "bureau", "taf"}
            if str(value).lower() in invalid_locations:
                logger.warning(f"Invalid location rejected: '{value}'")
                return None

        # Convertir age en int si c'est une string
        if fact_type == "age":
            try:
                value = int(value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid age value: {value}")
                return None

        current_value = current_user.get(fact_type)
        if value != current_value:
            # Pour "name" et "age": ne PAS écraser si une valeur existe et importance < 8
            # (importance 6 = famille/ami, importance 8+ = info du user lui-même)
            if fact_type in ["name", "age"] and current_value and fact.get("importance", 5) < 8:
                logger.info(f"Skipping {fact_type} override: '{value}' (importance {fact.get('importance')}) won't replace '{current_value}'")
                return None
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
        event_type=event_type,
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
