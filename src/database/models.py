import asyncpg
import logging
from datetime import datetime, date
from typing import Optional, Dict, List
from config.settings import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Initialize database connection pool"""
        self.pool = await asyncpg.create_pool(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            min_size=2,
            max_size=10
        )
        await self._create_tables()
        logger.info("Database connected")
    
    async def _create_tables(self):
        """Create tables if they don't exist"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    language_code VARCHAR(10) DEFAULT 'en',
                    subscription_tier VARCHAR(50) DEFAULT 'free',
                    subscription_expires_at TIMESTAMP,
                    messages_today INT DEFAULT 0,
                    last_message_date DATE,
                    gems INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id),
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id),
                    content TEXT NOT NULL,
                    memory_type VARCHAR(50) DEFAULT 'semantic',
                    importance FLOAT DEFAULT 5.0,
                    access_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS luna_states (
                    id SERIAL PRIMARY KEY,
                    user_id INT UNIQUE REFERENCES users(id),
                    affection_level FLOAT DEFAULT 10,
                    relationship_stage VARCHAR(50) DEFAULT 'strangers',
                    last_interaction TIMESTAMP DEFAULT NOW(),
                    streak_days INT DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Conversation state persistence
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_states (
                    id SERIAL PRIMARY KEY,
                    user_id INT UNIQUE REFERENCES users(id),
                    current_state VARCHAR(50) DEFAULT 'greeting',
                    mood VARCHAR(50) DEFAULT 'happy',
                    energy INT DEFAULT 7,
                    arousal INT DEFAULT 0,
                    trust FLOAT DEFAULT 20,
                    attraction FLOAT DEFAULT 15,
                    comfort FLOAT DEFAULT 10,
                    session_start TIMESTAMP DEFAULT NOW(),
                    has_nsfw_history BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Memory tiers
            await conn.execute("""
                ALTER TABLE memories
                ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'long'
            """)

            # Index for faster memory queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_tier
                ON memories(user_id, tier)
            """)
    
    async def get_or_create_user(self, telegram_id: int, username: str = None,
                                   first_name: str = None, language_code: str = 'en') -> Dict:
        """Get existing user or create new one"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )
            
            if user:
                return dict(user)
            
            # Create new user
            user = await conn.fetchrow("""
                INSERT INTO users (telegram_id, username, first_name, language_code)
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """, telegram_id, username, first_name, language_code)
            
            user_id = user['id']
            
            # Create luna_state for this user
            await conn.execute("""
                INSERT INTO luna_states (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)
            
            logger.info(f"Created new user: {telegram_id}")
            return dict(user)
    
    async def update_user(self, user_id: int, **kwargs) -> None:
        """Update user fields"""
        if not kwargs:
            return
        
        set_clauses = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values())
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE users SET {set_clauses}, updated_at = NOW() WHERE id = $1",
                user_id, *values
            )
    
    async def get_conversation_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get recent conversation history"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, created_at
                FROM messages
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)
            
            return [dict(r) for r in reversed(rows)]
    
    async def store_message(self, user_id: int, role: str, content: str) -> None:
        """Store a message in history"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO messages (user_id, role, content)
                VALUES ($1, $2, $3)
            """, user_id, role, content)
    
    async def get_luna_state(self, user_id: int) -> Dict:
        """Get Luna's state for this user"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM luna_states WHERE user_id = $1", user_id
            )
            
            if row:
                return dict(row)
            
            # Create if doesn't exist
            await conn.execute(
                "INSERT INTO luna_states (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            return {"affection_level": 10, "relationship_stage": "strangers", "streak_days": 0}
    
    async def get_messages_today(self, user_id: int) -> int:
        """Get number of messages sent today"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT messages_today, last_message_date FROM users WHERE id = $1",
                user_id
            )
            
            if not row:
                return 0
            
            last_date = row['last_message_date']
            today = date.today()
            
            if last_date != today:
                # Reset counter for new day
                await conn.execute(
                    "UPDATE users SET messages_today = 0, last_message_date = $2 WHERE id = $1",
                    user_id, today
                )
                return 0
            
            return row['messages_today'] or 0
    
    async def increment_message_count(self, user_id: int) -> None:
        """Increment today's message count"""
        async with self.pool.acquire() as conn:
            today = date.today()
            await conn.execute("""
                UPDATE users 
                SET messages_today = messages_today + 1,
                    last_message_date = $2,
                    updated_at = NOW()
                WHERE id = $1
            """, user_id, today)
    
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()

    # === CONVERSATION STATE PERSISTENCE ===

    async def get_conversation_state(self, user_id: int) -> Dict:
        """Get persisted conversation state"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversation_states WHERE user_id = $1", user_id
            )
            if row:
                return dict(row)

            # Create default state
            await conn.execute("""
                INSERT INTO conversation_states (user_id)
                VALUES ($1) ON CONFLICT (user_id) DO NOTHING
            """, user_id)
            return {
                "current_state": "greeting",
                "mood": "happy",
                "energy": 7,
                "arousal": 0,
                "trust": 20,
                "attraction": 15,
                "comfort": 10,
                "has_nsfw_history": False
            }

    async def save_conversation_state(self, user_id: int, state: Dict) -> None:
        """Save conversation state to DB"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO conversation_states
                    (user_id, current_state, mood, energy, arousal, trust, attraction, comfort, has_nsfw_history)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id) DO UPDATE SET
                    current_state = $2,
                    mood = $3,
                    energy = $4,
                    arousal = $5,
                    trust = $6,
                    attraction = $7,
                    comfort = $8,
                    has_nsfw_history = $9,
                    updated_at = NOW()
            """, user_id,
                state.get('current_state', 'greeting'),
                state.get('mood', 'happy'),
                state.get('energy', 7),
                state.get('arousal', 0),
                state.get('trust', 20),
                state.get('attraction', 15),
                state.get('comfort', 10),
                state.get('has_nsfw_history', False)
            )

    async def mark_nsfw_history(self, user_id: int) -> None:
        """Mark that this user has NSFW in their history"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE conversation_states
                SET has_nsfw_history = TRUE, updated_at = NOW()
                WHERE user_id = $1
            """, user_id)

    # === MEMORY TIERS ===

    async def store_memory(self, user_id: int, content: str, tier: str = 'long',
                          memory_type: str = 'semantic', importance: float = 5.0) -> None:
        """Store a memory with tier classification"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO memories (user_id, content, tier, memory_type, importance)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, content, tier, memory_type, importance)

    async def get_memories_by_tier(self, user_id: int, tier: str, limit: int = 10) -> List[Dict]:
        """Get memories by tier"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT content, memory_type, importance, created_at
                FROM memories
                WHERE user_id = $1 AND tier = $2
                ORDER BY importance DESC, created_at DESC
                LIMIT $3
            """, user_id, tier, limit)
            return [dict(r) for r in rows]

    async def get_all_memories_tiered(self, user_id: int) -> Dict[str, List[Dict]]:
        """Get all memories organized by tier"""
        short = await self.get_memories_by_tier(user_id, 'short', 5)
        mid = await self.get_memories_by_tier(user_id, 'mid', 10)
        long = await self.get_memories_by_tier(user_id, 'long', 10)
        return {'short': short, 'mid': mid, 'long': long}

    async def clear_short_term_memories(self, user_id: int) -> None:
        """Clear short-term memories (session reset)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM memories
                WHERE user_id = $1 AND tier = 'short'
            """, user_id)

    async def promote_memory(self, user_id: int, content: str, from_tier: str, to_tier: str) -> None:
        """Promote a memory from one tier to another"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE memories
                SET tier = $3, importance = importance + 2
                WHERE user_id = $1 AND content = $2 AND tier = $4
            """, user_id, to_tier, content, from_tier)


db = Database()
