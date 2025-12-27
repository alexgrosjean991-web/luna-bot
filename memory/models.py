"""
Memory System - Database Models

Tables:
- users: Infos sur l'utilisateur (facts)
- relationships: État de la relation avec Luna
- timeline: Événements importants (moments, promesses, luna_said, etc.)
"""

# SQL pour créer les tables
# À exécuter via init_memory_tables()

USERS_TABLE = """
CREATE TABLE IF NOT EXISTS memory_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,

    -- Facts basiques
    name VARCHAR(100),
    age INTEGER,
    job VARCHAR(200),
    location VARCHAR(200),
    timezone VARCHAR(50) DEFAULT 'Europe/Paris',

    -- Facts complexes (listes)
    likes JSONB DEFAULT '[]',
    dislikes JSONB DEFAULT '[]',
    secrets JSONB DEFAULT '[]',
    family JSONB DEFAULT '{}',

    -- Préférences NSFW
    nsfw_prefs JSONB DEFAULT '{"likes":[],"dislikes":[],"limits":[]}',

    -- État temps réel (au lieu de Redis)
    state JSONB DEFAULT '{"luna_mood":"neutral","current_topic":null}',

    -- === V2: MEMORY PREMIUM ===

    -- Patterns détectés sur l'user
    user_patterns JSONB DEFAULT '{}',
    -- Structure: {"active_hours": [20,21,22], "mood_triggers": ["travail"], "communication_style": "direct"}

    -- Dates importantes à venir
    calendar_dates JSONB DEFAULT '[]',
    -- Structure: [{"date": "2025-02-14", "event": "notre 1 mois", "type": "anniversary", "importance": 9}]

    -- Vie de Luna (état actuel pour immersion)
    luna_current_life JSONB DEFAULT '{}',
    -- Structure: {"mood": "chill", "current_project": "refonte site", "pixel_status": "dort", "recent_event": null}

    -- Tracking compression
    last_memory_extraction TIMESTAMP WITH TIME ZONE,
    last_weekly_summary TIMESTAMP WITH TIME ZONE,
    last_monthly_cleanup TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_users_telegram
ON memory_users(telegram_id);
"""

RELATIONSHIPS_TABLE = """
CREATE TABLE IF NOT EXISTS memory_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES memory_users(id) ON DELETE CASCADE UNIQUE,

    -- Progression
    day INTEGER DEFAULT 1,
    intimacy INTEGER DEFAULT 1 CHECK (intimacy >= 1 AND intimacy <= 10),
    trust INTEGER DEFAULT 1 CHECK (trust >= 1 AND trust <= 10),
    status VARCHAR(20) DEFAULT 'new',  -- new, flirty, close, deep, intimate

    -- Éléments relationnels
    inside_jokes JSONB DEFAULT '[]',
    pet_names JSONB DEFAULT '[]',
    shared_memories JSONB DEFAULT '[]',

    -- Abonnement
    paid BOOLEAN DEFAULT FALSE,
    paid_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    first_contact TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_rel_user
ON memory_relationships(user_id);
"""

SUMMARIES_TABLE = """
CREATE TABLE IF NOT EXISTS memory_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES memory_users(id) ON DELETE CASCADE,

    -- Type de résumé
    type VARCHAR(20) NOT NULL,  -- 'weekly' ou 'monthly'
    period VARCHAR(20) NOT NULL,  -- '2025-W03' ou '2025-01'

    -- Contenu
    summary TEXT NOT NULL,
    highlights JSONB DEFAULT '[]',  -- ["premier je t'aime", "dispute résolue"]
    archived_data JSONB DEFAULT '{}',  -- Données archivées (jokes inactifs, events compressés)

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_summaries_user_type
ON memory_summaries(user_id, type);

CREATE INDEX IF NOT EXISTS idx_summaries_period
ON memory_summaries(user_id, period);
"""

TIMELINE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_timeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES memory_users(id) ON DELETE CASCADE,

    -- Type d'événement
    type VARCHAR(50) NOT NULL,
    -- Types possibles:
    -- 'moment': événement important vécu par user
    -- 'luna_said': ce que Luna a révélé sur elle
    -- 'promise': promesse faite (par user ou Luna)
    -- 'conflict': tension/dispute
    -- 'milestone': premier "je t'aime", premier NSFW, etc.
    -- 'contradiction': incohérence détectée

    -- Contenu
    summary TEXT NOT NULL,
    keywords JSONB DEFAULT '[]',

    -- Importance
    score INTEGER DEFAULT 7 CHECK (score >= 1 AND score <= 10),
    tier VARCHAR(10) DEFAULT 'hot',  -- hot (récent), warm (7-90j), cold (>90j)
    pinned BOOLEAN DEFAULT FALSE,  -- Toujours inclure dans context

    -- Timestamps
    event_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index pour queries rapides
CREATE INDEX IF NOT EXISTS idx_timeline_user_tier
ON memory_timeline(user_id, tier);

CREATE INDEX IF NOT EXISTS idx_timeline_user_type
ON memory_timeline(user_id, type);

CREATE INDEX IF NOT EXISTS idx_timeline_keywords
ON memory_timeline USING GIN(keywords);

CREATE INDEX IF NOT EXISTS idx_timeline_pinned
ON memory_timeline(user_id, pinned) WHERE pinned = TRUE;
"""

# Types pour le code Python
from typing import TypedDict, Optional
from datetime import datetime


class UserFacts(TypedDict, total=False):
    """Facts sur l'utilisateur."""
    name: Optional[str]
    age: Optional[int]
    job: Optional[str]
    location: Optional[str]
    timezone: str
    likes: list[str]
    dislikes: list[str]
    secrets: list[str]
    family: dict
    nsfw_prefs: dict


class RelationshipState(TypedDict, total=False):
    """État de la relation."""
    day: int
    intimacy: int  # 1-10
    trust: int  # 1-10
    status: str  # new, flirty, close, deep, intimate
    inside_jokes: list[str]
    pet_names: list[str]
    paid: bool


class TimelineEvent(TypedDict):
    """Événement dans la timeline."""
    id: str
    type: str  # moment, luna_said, promise, conflict, milestone, contradiction
    summary: str
    keywords: list[str]
    score: int  # 1-10
    tier: str  # hot, warm, cold
    pinned: bool
    event_date: datetime


class LunaState(TypedDict, total=False):
    """État temps réel de Luna (stocké dans users.state)."""
    luna_mood: str  # neutral, playful, flirty, caring, vulnerable, horny
    current_topic: Optional[str]
    last_message_at: Optional[str]


class InsideJoke(TypedDict, total=False):
    """Inside joke enrichi avec tracking d'usage."""
    trigger: str  # Mot/phrase déclencheur
    context: str  # Pourquoi c'est drôle
    importance: int  # 1-10
    times_used: int  # Nombre de fois utilisé
    last_used: str  # ISO datetime
    created_at: str  # ISO datetime


class CalendarDate(TypedDict, total=False):
    """Date importante à venir."""
    date: str  # YYYY-MM-DD
    event: str  # Description
    type: str  # anniversary, promise, plan, birthday
    importance: int  # 1-10


class UserPatterns(TypedDict, total=False):
    """Patterns détectés sur l'utilisateur."""
    active_hours: list[int]  # Heures actives [20, 21, 22, 23]
    mood_triggers: list[str]  # Ce qui le rend triste/heureux
    communication_style: str  # direct, timide, bavard


class LunaCurrentLife(TypedDict, total=False):
    """Vie actuelle de Luna (pour immersion)."""
    mood: str  # chill, stressed, happy, tired
    current_project: Optional[str]  # "refonte site client"
    pixel_status: Optional[str]  # "dort sur mes genoux"
    recent_event: Optional[str]  # "call client stressant"


class WeeklySummary(TypedDict):
    """Résumé hebdomadaire."""
    week: str  # 2025-W03
    summary: str  # Résumé en 3-4 phrases
    highlights: list[str]  # Moments clés
    created_at: str  # ISO datetime


class MemoryContext(TypedDict):
    """Context complet pour le prompt."""
    user: UserFacts
    relationship: RelationshipState
    hot_events: list[TimelineEvent]
    relevant_events: list[TimelineEvent]
    luna_said: list[TimelineEvent]  # Ce que Luna a dit sur le topic actuel
    state: LunaState


# Event types constants
class EventType:
    MOMENT = "moment"
    LUNA_SAID = "luna_said"
    PROMISE = "promise"
    CONFLICT = "conflict"
    MILESTONE = "milestone"
    CONTRADICTION = "contradiction"


# Relationship status progression
class RelationshipStatus:
    NEW = "new"          # Jour 1-3
    FLIRTY = "flirty"    # Jour 4-14, intimacy 2+
    CLOSE = "close"      # Jour 15-30, intimacy 4+
    DEEP = "deep"        # Jour 31-60, intimacy 6+
    INTIMATE = "intimate"  # Jour 60+, intimacy 8+


# Tier thresholds (jours)
class TierThreshold:
    HOT_DAYS = 7      # Events < 7 jours = hot
    WARM_DAYS = 90    # Events 7-90 jours = warm
    # > 90 jours = cold


async def init_memory_tables(pool) -> None:
    """
    Initialise les tables mémoire.
    À appeler au démarrage du bot.
    """
    async with pool.acquire() as conn:
        await conn.execute(USERS_TABLE)
        await conn.execute(RELATIONSHIPS_TABLE)
        await conn.execute(SUMMARIES_TABLE)
        await conn.execute(TIMELINE_TABLE)

        # === MIGRATIONS V2 ===
        # Ajouter colonnes manquantes sur memory_users (si upgrade)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS user_patterns JSONB DEFAULT '{}';
        """)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS calendar_dates JSONB DEFAULT '[]';
        """)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS luna_current_life JSONB DEFAULT '{}';
        """)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS last_memory_extraction TIMESTAMP WITH TIME ZONE;
        """)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS last_weekly_summary TIMESTAMP WITH TIME ZONE;
        """)
        await conn.execute("""
            ALTER TABLE memory_users
            ADD COLUMN IF NOT EXISTS last_monthly_cleanup TIMESTAMP WITH TIME ZONE;
        """)

    print("Memory tables initialized")
