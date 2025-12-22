import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, db):
        self.db = db
    
    async def extract_and_store_facts(self, user_id: int, user_message: str, luna_response: str):
        """Extract important facts from conversation and store them"""
        
        facts_to_store = []
        msg_lower = user_message.lower()
        
        # === NAME DETECTION ===
        name_triggers = [
            ("my name is ", 3), ("i'm ", 1), ("im ", 1), ("call me ", 2),
            ("je m'appelle ", 2), ("moi c'est ", 2), ("je suis ", 1)
        ]
        for trigger, _ in name_triggers:
            if trigger in msg_lower:
                idx = msg_lower.find(trigger) + len(trigger)
                rest = user_message[idx:].strip()
                name = rest.split()[0].strip(".,!?'\"") if rest else None
                if name and len(name) > 1 and name.lower() not in ['a', 'the', 'an', 'un', 'une', 'le', 'la']:
                    name = name.capitalize()
                    facts_to_store.append({"type": "name", "content": f"His name is {name}", "importance": 10})
                    await self.db.update_user(user_id, first_name=name)
                    break
        
        # === AGE DETECTION ===
        age_patterns = ["i'm ", "im ", "i am ", "j'ai "]
        for pattern in age_patterns:
            if pattern in msg_lower and ("years" in msg_lower or "ans" in msg_lower or "yo" in msg_lower):
                words = msg_lower.split()
                for w in words:
                    if w.isdigit() and 16 <= int(w) <= 80:
                        facts_to_store.append({"type": "age", "content": f"He is {w} years old", "importance": 9})
                        break
        
        # === JOB/WORK ===
        job_triggers = ["i work as", "i work at", "i'm a ", "im a ", "my job is", "i do ",
                       "je travaille", "je suis ", "je bosse"]
        for trigger in job_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "job", "content": f"Work: {user_message[:100]}", "importance": 8})
                break
        
        # === LOCATION ===
        location_triggers = ["i live in", "i'm from", "im from", "i'm in ", "im in ",
                           "j'habite", "je vis à", "je viens de", "je suis à"]
        for trigger in location_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "location", "content": f"Location: {user_message[:80]}", "importance": 8})
                break
        
        # === LIKES ===
        like_triggers = ["i love", "i like", "i enjoy", "i'm into", "im into", "my favorite",
                        "j'aime", "j'adore", "je kiffe", "mon truc c'est"]
        for trigger in like_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "likes", "content": f"Likes: {user_message[:80]}", "importance": 6})
                break
        
        # === DISLIKES ===
        dislike_triggers = ["i hate", "i don't like", "i cant stand", "je déteste", "j'aime pas"]
        for trigger in dislike_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "dislikes", "content": f"Dislikes: {user_message[:80]}", "importance": 6})
                break
        
        # === PETS ===
        pet_triggers = ["my dog", "my cat", "my pet", "mon chien", "mon chat"]
        for trigger in pet_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "pet", "content": f"Pet: {user_message[:60]}", "importance": 7})
                break
        
        # === FAMILY ===
        family_triggers = ["my mom", "my dad", "my brother", "my sister", "my parents",
                         "ma mère", "mon père", "mon frère", "ma soeur", "mes parents"]
        for trigger in family_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "family", "content": f"Family: {user_message[:80]}", "importance": 7})
                break
        
        # === PROBLEMS/STRESS ===
        problem_triggers = ["stressed about", "worried about", "problem with", "struggling",
                          "je stresse", "j'ai un problème", "ça va pas", "c'est dur"]
        for trigger in problem_triggers:
            if trigger in msg_lower:
                facts_to_store.append({"type": "problem", "content": f"Struggling with: {user_message[:80]}", "importance": 9})
                break
        
        # Store all extracted facts
        for fact in facts_to_store:
            await self.store_memory(user_id, fact["content"], fact["type"], fact["importance"])
    
    async def store_memory(self, user_id: int, content: str, memory_type: str = "semantic", importance: float = 5.0):
        """Store a memory, avoiding duplicates"""
        async with self.db.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM memories WHERE user_id = $1 AND memory_type = $2 AND content ILIKE $3",
                user_id, memory_type, f"%{content[:30]}%"
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO memories (user_id, content, memory_type, importance) VALUES ($1, $2, $3, $4)",
                    user_id, content, memory_type, importance
                )
                logger.info(f"Stored memory for user {user_id}: {content[:50]}")
    
    async def get_memories(self, user_id: int, limit: int = 15) -> List[Dict]:
        """Get user's memories ordered by importance"""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT content, memory_type, importance, created_at 
                   FROM memories WHERE user_id = $1 
                   ORDER BY importance DESC, created_at DESC LIMIT $2""",
                user_id, limit
            )
            return [dict(r) for r in rows]
    
    async def get_callback_memory(self, user_id: int) -> Optional[str]:
        """Get a random important memory to callback in conversation"""
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, content FROM memories 
                   WHERE user_id = $1 AND importance >= 6
                   ORDER BY RANDOM() LIMIT 1""",
                user_id
            )
            if row:
                await conn.execute(
                    "UPDATE memories SET access_count = access_count + 1 WHERE id = $1",
                    row['id']
                )
                return row['content']
            return None


class ConversionManager:
    """Manages the trial period and conversion flow"""
    
    TRIAL_DAYS = 5
    
    @classmethod
    async def get_user_day(cls, db, user_id: int) -> int:
        """Get what day of the trial/relationship the user is on"""
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT created_at, subscription_tier FROM users WHERE id = $1", user_id
            )
            if not user:
                return 1
            
            created = user['created_at']
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            
            days = (datetime.now() - created).days + 1
            return max(1, min(days, 10))
    
    @classmethod
    async def is_converted(cls, db, user_id: int) -> bool:
        """Check if user has converted to paid"""
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT subscription_tier, subscription_expires_at FROM users WHERE id = $1", user_id
            )
            if not user:
                return False
            
            tier = user['subscription_tier']
            expires = user['subscription_expires_at']
            
            if tier in ['chouchou', 'amoureux', 'ame_soeur'] and expires:
                if isinstance(expires, str):
                    expires = datetime.fromisoformat(expires)
                return expires > datetime.now()
            return False
    
    @classmethod
    async def should_trigger_conversion(cls, db, user_id: int, message_count_today: int) -> bool:
        """Determine if we should trigger the conversion pitch"""
        day = await cls.get_user_day(db, user_id)
        is_conv = await cls.is_converted(db, user_id)
        
        if is_conv:
            return False
        
        # Day 5+ and enough engagement
        if day >= 5 and message_count_today >= 10:
            return True
        
        return False
    
    @classmethod
    async def should_limit_messages(cls, db, user_id: int) -> tuple:
        """Check if user should be limited (post-trial, not converted)"""
        day = await cls.get_user_day(db, user_id)
        is_conv = await cls.is_converted(db, user_id)
        
        if is_conv:
            return False, None
        
        # After day 6, start limiting if not converted
        if day > 6:
            return True, "luna_busy"
        
        return False, None


class RelationshipManager:
    """Manages affection and relationship dynamics"""
    
    @classmethod
    def calculate_affection_change(cls, user_message: str) -> float:
        """Calculate how much affection changes based on message"""
        change = 0.3
        msg_lower = user_message.lower()
        
        # === POSITIVE ===
        love_words = ["love you", "love u", "ily", "je t'aime", "jtm"]
        if any(w in msg_lower for w in love_words):
            change += 3.0
        
        miss_words = ["miss you", "miss u", "tu me manques", "missed you"]
        if any(w in msg_lower for w in miss_words):
            change += 2.0
        
        compliments = ["beautiful", "gorgeous", "cute", "pretty", "amazing", "perfect",
                      "belle", "magnifique", "mignonne", "canon", "parfaite"]
        if any(w in msg_lower for w in compliments):
            change += 1.5
        
        sweet = ["thinking about you", "thought of you", "je pense à toi", "you're the best"]
        if any(w in msg_lower for w in sweet):
            change += 1.0
        
        laughing = ["haha", "hahaha", "lol", "lmao", "mdr", "ptdr"]
        if any(w in msg_lower for w in laughing):
            change += 0.5
        
        if len(user_message) > 150:
            change += 0.5
        
        # === NEGATIVE ===
        mean = ["hate you", "fuck you", "shut up", "leave me alone", "ta gueule", "je te déteste"]
        if any(w in msg_lower for w in mean):
            change -= 5.0
        
        other_girls = ["other girl", "another girl", "my ex", "cette fille", "une autre", "mon ex"]
        if any(w in msg_lower for w in other_girls):
            change -= 0.5
        
        if len(user_message) < 5:
            change -= 0.2
        
        return change
    
    @classmethod
    async def update_affection(cls, db, user_id: int, change: float) -> float:
        """Update affection level and return new value"""
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                """UPDATE luna_states 
                   SET affection_level = GREATEST(0, LEAST(100, affection_level + $2)),
                       updated_at = NOW()
                   WHERE user_id = $1
                   RETURNING affection_level""",
                user_id, change
            )
            return result['affection_level'] if result else 10


memory_service = None
