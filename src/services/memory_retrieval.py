"""
Memory Retrieval Service
Récupère les mémoires pertinentes au contexte actuel.
Utilise TF-IDF + temporal decay + importance scoring.
"""

import logging
import math
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScoredMemory:
    """Mémoire avec son score de pertinence"""
    content: str
    memory_type: str
    tier: str
    importance: float
    created_at: datetime
    relevance_score: float
    decay_factor: float
    final_score: float


class MemoryRetrieval:
    """
    Système de retrieval intelligent pour les mémoires.

    Scoring formula:
    final_score = relevance_score * decay_factor * importance_weight * type_boost
    """

    # Boost par type de mémoire selon le contexte
    TYPE_BOOSTS = {
        'fact': 1.0,        # Toujours pertinent
        'preference': 1.2,  # Important pour personnalisation
        'emotion': 0.8,     # Contextuel
        'event': 1.1,       # Souvent référencé
        'relationship': 1.3 # Très important pour le ton
    }

    # Mots vides français/anglais
    STOPWORDS = {
        'le', 'la', 'les', 'un', 'une', 'des', 'de', 'du', 'et', 'est', 'en',
        'que', 'qui', 'dans', 'pour', 'sur', 'avec', 'ce', 'il', 'elle', 'je',
        'tu', 'nous', 'vous', 'ils', 'elles', 'son', 'sa', 'ses', 'mon', 'ma',
        'mes', 'ton', 'ta', 'tes', 'au', 'aux', 'ne', 'pas', 'plus', 'aussi',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'to', 'of', 'in',
        'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
        'j\'', 't\'', 'c\'', 's\'', 'd\'', 'l\'', 'n\'', 'qu\'',
        'mdr', 'lol', 'oui', 'non', 'ok', 'ah', 'oh', 'hm', 'euh'
    }

    # Keywords qui indiquent des sujets importants
    TOPIC_KEYWORDS = {
        'travail': ['boulot', 'taf', 'job', 'boss', 'collègue', 'réunion', 'projet', 'work'],
        'famille': ['père', 'mère', 'frère', 'soeur', 'parent', 'famille', 'maman', 'papa'],
        'relation': ['ex', 'copain', 'copine', 'crush', 'date', 'rencard', 'mec', 'meuf'],
        'hobby': ['sport', 'musique', 'film', 'série', 'jeu', 'game', 'livre', 'anime'],
        'lieu': ['paris', 'lyon', 'ville', 'appart', 'maison', 'chez'],
        'emotion': ['triste', 'content', 'heureux', 'énervé', 'stressé', 'fatigué', 'love'],
        'futur': ['demain', 'weekend', 'vacances', 'projet', 'envie', 'rêve', 'plan']
    }

    def __init__(self, db):
        self.db = db
        self._idf_cache: Dict[str, float] = {}

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize et normalise le texte"""
        text = text.lower()
        # Remove punctuation except apostrophes
        text = re.sub(r'[^\w\s\']', ' ', text)
        tokens = text.split()
        # Remove stopwords and short tokens
        tokens = [t for t in tokens if t not in self.STOPWORDS and len(t) > 2]
        return tokens

    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Compute term frequency"""
        counts = Counter(tokens)
        total = len(tokens) if tokens else 1
        return {token: count / total for token, count in counts.items()}

    def _compute_relevance(self, query_tokens: List[str], memory_tokens: List[str]) -> float:
        """
        Compute relevance score entre query et memory.
        Utilise Jaccard similarity + term overlap.
        """
        if not query_tokens or not memory_tokens:
            return 0.0

        query_set = set(query_tokens)
        memory_set = set(memory_tokens)

        # Jaccard similarity
        intersection = len(query_set & memory_set)
        union = len(query_set | memory_set)
        jaccard = intersection / union if union > 0 else 0.0

        # Term overlap (plus de poids aux matches)
        overlap_count = sum(1 for t in query_tokens if t in memory_set)
        overlap_ratio = overlap_count / len(query_tokens) if query_tokens else 0.0

        # Combinaison
        return (jaccard * 0.4) + (overlap_ratio * 0.6)

    def _compute_decay(self, created_at: datetime, half_life_days: float = 30.0) -> float:
        """
        Compute temporal decay factor.
        Plus la mémoire est vieille, moins elle pèse.

        half_life_days: Temps pour que le score soit divisé par 2
        """
        if not created_at:
            return 0.5

        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (now - created_at).total_seconds() / 86400

        # Exponential decay: e^(-lambda * t) where lambda = ln(2) / half_life
        decay_constant = math.log(2) / half_life_days
        decay = math.exp(-decay_constant * age_days)

        # Clamp entre 0.1 et 1.0 (jamais complètement oublié)
        return max(0.1, min(1.0, decay))

    def _detect_topics(self, text: str) -> List[str]:
        """Détecte les sujets mentionnés dans le texte"""
        text_lower = text.lower()
        detected = []

        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected.append(topic)

        return detected

    def _boost_by_topic_match(self, query_topics: List[str], memory_content: str) -> float:
        """Boost si les sujets matchent"""
        if not query_topics:
            return 1.0

        memory_topics = self._detect_topics(memory_content)
        matching = set(query_topics) & set(memory_topics)

        if matching:
            return 1.0 + (0.3 * len(matching))  # +30% par sujet qui matche
        return 1.0

    async def retrieve_relevant(
        self,
        user_id: int,
        query: str,
        context_messages: List[Dict] = None,
        max_memories: int = 8,
        min_score: float = 0.1
    ) -> List[ScoredMemory]:
        """
        Récupère les mémoires les plus pertinentes pour le contexte actuel.

        Args:
            user_id: ID de l'utilisateur
            query: Message actuel de l'utilisateur
            context_messages: Messages récents pour contexte additionnel
            max_memories: Nombre max de mémoires à retourner
            min_score: Score minimum pour inclure une mémoire

        Returns:
            Liste de ScoredMemory triées par pertinence
        """
        # Build full query context
        full_query = query
        if context_messages:
            # Add last 3 user messages to query context
            user_msgs = [m['content'] for m in context_messages[-6:] if m.get('role') == 'user']
            full_query = ' '.join(user_msgs[-3:] + [query])

        query_tokens = self._tokenize(full_query)
        query_topics = self._detect_topics(full_query)

        logger.info(f"Query tokens: {query_tokens[:10]}...")
        logger.info(f"Detected topics: {query_topics}")

        # Get all memories from DB
        all_memories = await self._get_all_memories(user_id)

        if not all_memories:
            logger.info("No memories found for user")
            return []

        scored_memories = []

        for memory in all_memories:
            content = memory.get('content', '')
            memory_tokens = self._tokenize(content)

            # Compute scores
            relevance = self._compute_relevance(query_tokens, memory_tokens)
            decay = self._compute_decay(memory.get('created_at'))
            importance = memory.get('importance', 5.0) / 10.0  # Normalize to 0-1
            type_boost = self.TYPE_BOOSTS.get(memory.get('memory_type', 'fact'), 1.0)
            topic_boost = self._boost_by_topic_match(query_topics, content)

            # Tier boost (long-term = more established facts)
            tier = memory.get('tier', 'long')
            tier_boost = {'long': 1.2, 'mid': 1.0, 'short': 0.8}.get(tier, 1.0)

            # Final score
            final_score = relevance * decay * importance * type_boost * topic_boost * tier_boost

            if final_score >= min_score or relevance > 0.3:  # Include high relevance even if low score
                scored_memories.append(ScoredMemory(
                    content=content,
                    memory_type=memory.get('memory_type', 'fact'),
                    tier=tier,
                    importance=memory.get('importance', 5.0),
                    created_at=memory.get('created_at'),
                    relevance_score=relevance,
                    decay_factor=decay,
                    final_score=final_score
                ))

        # Sort by final score descending
        scored_memories.sort(key=lambda m: m.final_score, reverse=True)

        # Take top N
        result = scored_memories[:max_memories]

        logger.info(f"Retrieved {len(result)} relevant memories (from {len(all_memories)} total)")
        for m in result[:3]:
            logger.info(f"  - [{m.memory_type}] {m.content[:50]}... (score={m.final_score:.3f})")

        return result

    async def _get_all_memories(self, user_id: int) -> List[Dict]:
        """Get all memories for a user"""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT content, memory_type, tier, importance, created_at
                FROM memories
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 100
            """, user_id)
            return [dict(r) for r in rows]

    def format_for_prompt(
        self,
        memories: List[ScoredMemory],
        max_chars: int = 500
    ) -> str:
        """
        Formate les mémoires pour inclusion dans le prompt.
        Groupé par catégorie pour meilleure lisibilité.
        """
        if not memories:
            return "Tu sais pas grand chose sur lui encore."

        # Group by type
        by_type = {}
        for m in memories:
            mtype = m.memory_type
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(m.content)

        # Format with type headers
        sections = []
        type_labels = {
            'fact': '📋 Faits',
            'preference': '❤️ Préférences',
            'emotion': '💭 État récent',
            'event': '📅 Événements',
            'relationship': '💕 Relation'
        }

        for mtype, contents in by_type.items():
            label = type_labels.get(mtype, mtype.capitalize())
            items = '\n'.join([f"- {c}" for c in contents[:3]])
            sections.append(f"{label}:\n{items}")

        result = '\n'.join(sections)

        # Truncate if too long
        if len(result) > max_chars:
            result = result[:max_chars-3] + "..."

        return result

    async def get_contextual_memories(
        self,
        user_id: int,
        current_message: str,
        history: List[Dict] = None
    ) -> str:
        """
        High-level method: récupère et formate les mémoires pertinentes.
        Appelé par le prompt_assembler.
        """
        memories = await self.retrieve_relevant(
            user_id=user_id,
            query=current_message,
            context_messages=history,
            max_memories=8
        )

        return self.format_for_prompt(memories)


# Singleton
_retrieval: Optional[MemoryRetrieval] = None


def get_memory_retrieval(db) -> MemoryRetrieval:
    global _retrieval
    if _retrieval is None:
        _retrieval = MemoryRetrieval(db)
    return _retrieval
