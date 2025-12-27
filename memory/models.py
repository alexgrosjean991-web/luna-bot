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
        await conn.execute(TIMELINE_TABLE)

    print("Memory tables initialized")
