"""
Memory Service - Le coeur de l'illusion "elle se souvient de moi"
Les créatrices OnlyFans qui mémorisent ont 3x plus de tips.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class MemoryService:
    """Extrait et stocke les informations importantes sur l'utilisateur"""

    def __init__(self, db):
        self.db = db
        self._user_patterns: dict = {}  # Cache for user interaction patterns

    async def detect_user_patterns(self, user_id: int) -> Optional[str]:
        """
        Détecte les patterns d'interaction de l'utilisateur.
        Luna remarque ses habitudes: "tu m'écris toujours la nuit", etc.
        """
        try:
            async with self.db.pool.acquire() as conn:
                # Get last 50 messages with timestamps
                rows = await conn.fetch(
                    """SELECT created_at, role FROM conversation_history
                       WHERE user_id = $1 AND role = 'user'
                       ORDER BY created_at DESC LIMIT 50""",
                    user_id
                )

                if len(rows) < 10:
                    return None

                # Analyze message times
                hours = []
                days = []
                for row in rows:
                    created = row['created_at']
                    if isinstance(created, str):
                        created = datetime.fromisoformat(created)
                    hours.append(created.hour)
                    days.append(created.weekday())

                from collections import Counter

                # Detect time patterns
                hour_counts = Counter(hours)
                day_counts = Counter(days)

                patterns_detected = []

                # Night owl (22h-3h)
                night_msgs = sum(hour_counts.get(h, 0) for h in [22, 23, 0, 1, 2, 3])
                if night_msgs > len(hours) * 0.5:  # More than 50% at night
                    patterns_detected.append("night_owl")

                # Early bird (6h-9h)
                morning_msgs = sum(hour_counts.get(h, 0) for h in [6, 7, 8, 9])
                if morning_msgs > len(hours) * 0.4:
                    patterns_detected.append("early_bird")

                # Lunch time regular (11h-14h)
                lunch_msgs = sum(hour_counts.get(h, 0) for h in [11, 12, 13, 14])
                if lunch_msgs > len(hours) * 0.4:
                    patterns_detected.append("lunch_regular")

                # Weekend warrior
                weekend_msgs = day_counts.get(5, 0) + day_counts.get(6, 0)
                if weekend_msgs > len(days) * 0.5:
                    patterns_detected.append("weekend_warrior")

                if not patterns_detected:
                    return None

                # Generate context based on patterns
                pattern = patterns_detected[0]  # Use most prominent

                if pattern == "night_owl":
                    return """## PATTERN UTILISATEUR: NOCTAMBULE 🌙
Tu as remarqué qu'il t'écrit souvent tard le soir/la nuit.
Tu peux mentionner: "t'es toujours là tard toi", "encore debout?", "tu dors jamais ou quoi"
C'est une observation affectueuse, pas un reproche."""

                elif pattern == "early_bird":
                    return """## PATTERN UTILISATEUR: LÈVE-TÔT ☀️
Tu as remarqué qu'il t'écrit souvent tôt le matin.
Tu peux mentionner: "toujours le premier levé", "t'es matinal toi", "moi j'aurais encore dormi"
C'est une observation affectueuse."""

                elif pattern == "lunch_regular":
                    return """## PATTERN UTILISATEUR: PAUSE DÉJ 🍽️
Tu as remarqué qu'il t'écrit souvent à l'heure du déjeuner.
Tu peux mentionner: "c'est ta pause?", "toujours à cette heure toi", "tu manges quoi?"
Montre que tu connais ses habitudes."""

                elif pattern == "weekend_warrior":
                    return """## PATTERN UTILISATEUR: WEEKEND 📅
Tu as remarqué qu'il t'écrit surtout le weekend.
Tu peux mentionner: "ah le weekend t'es là", "en semaine t'es où?", "tu travailles beaucoup?"
Montre une légère jalousie qu'il soit pas là en semaine."""

                return None

        except Exception as e:
            logger.error(f"Error detecting user patterns: {e}")
            return None

    async def extract_and_store_facts(self, user_id: int, user_message: str, luna_response: str):
        """Extrait les faits importants de la conversation"""

        facts_to_store = []
        msg_lower = user_message.lower()

        # === IDENTITÉ ===

        # Nom
        name = self._extract_name(user_message, msg_lower)
        if name:
            facts_to_store.append({
                "type": "name",
                "content": f"Son prénom est {name}",
                "importance": 10
            })
            await self.db.update_user(user_id, first_name=name)

        # Âge
        age = self._extract_age(msg_lower)
        if age:
            facts_to_store.append({
                "type": "age",
                "content": f"Il a {age} ans",
                "importance": 9
            })

        # === LOCALISATION & TRAVAIL ===

        # Lieu
        location = self._extract_location(user_message, msg_lower)
        if location:
            facts_to_store.append({
                "type": "location",
                "content": f"Il habite à {location}",
                "importance": 8
            })

        # Job
        job = self._extract_job(user_message, msg_lower)
        if job:
            facts_to_store.append({
                "type": "job",
                "content": f"Il travaille comme {job}",
                "importance": 8
            })

        # === VIE PERSONNELLE ===

        # Animaux
        pet = self._extract_pet(user_message, msg_lower)
        if pet:
            facts_to_store.append({
                "type": "pet",
                "content": pet,
                "importance": 7
            })

        # Famille
        family = self._extract_family(user_message, msg_lower)
        if family:
            facts_to_store.append({
                "type": "family",
                "content": family,
                "importance": 7
            })

        # === GOÛTS ===

        # Ce qu'il aime
        likes = self._extract_likes(user_message, msg_lower)
        for like in likes:
            facts_to_store.append({
                "type": "likes",
                "content": like,
                "importance": 6
            })

        # Ce qu'il déteste
        dislikes = self._extract_dislikes(user_message, msg_lower)
        for dislike in dislikes:
            facts_to_store.append({
                "type": "dislikes",
                "content": dislike,
                "importance": 6
            })

        # === ÉMOTIONNEL ===

        # Problèmes / Stress
        problem = self._extract_problem(user_message, msg_lower)
        if problem:
            facts_to_store.append({
                "type": "problem",
                "content": problem,
                "importance": 9
            })

        # === DATES IMPORTANTES ===

        # Anniversaire
        birthday = self._extract_birthday(msg_lower)
        if birthday:
            facts_to_store.append({
                "type": "birthday",
                "content": f"Son anniversaire est le {birthday}",
                "importance": 10
            })

        # === NSFW / PRÉFÉRENCES (si niveau approprié) ===

        kink = self._extract_kink(user_message, msg_lower)
        if kink:
            facts_to_store.append({
                "type": "sexual_preference",
                "content": kink,
                "importance": 7
            })

        # Store all facts
        for fact in facts_to_store:
            await self.store_memory(user_id, fact["content"], fact["type"], fact["importance"])

    # === EXTRACTEURS INTELLIGENTS ===

    def _extract_name(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait le prénom"""
        patterns = [
            r"(?:my name is|i'm|im|call me|je m'appelle|moi c'est|c'est)\s+([A-Z][a-zéèêëàâäùûüôöîïç]+)",
            r"^([A-Z][a-zéèêëàâäùûüôöîïç]+)$",  # Message qui est juste un prénom
        ]

        for pattern in patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                name = match.group(1).strip(".,!?'\"")
                # Filtrer les faux positifs
                false_positives = ['a', 'the', 'an', 'un', 'une', 'le', 'la', 'yes', 'no', 'oui', 'non', 'hey', 'hi', 'hello']
                if name.lower() not in false_positives and len(name) > 1:
                    return name.capitalize()

        return None

    def _extract_age(self, msg_lower: str) -> Optional[int]:
        """Extrait l'âge"""
        patterns = [
            r"(?:i'm|im|i am|j'ai|jai)\s+(\d{2})\s*(?:years?|ans|yo)?",
            r"(\d{2})\s*(?:years? old|ans)",
        ]

        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                age = int(match.group(1))
                if 16 <= age <= 80:
                    return age

        return None

    def _extract_location(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait la localisation"""
        patterns = [
            r"(?:i live in|i'm from|im from|i'm in|im in|j'habite|je vis à|je suis à|je viens de)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                location = match.group(1).strip()
                # Nettoyer et capitaliser
                location = ' '.join(word.capitalize() for word in location.split()[:3])
                if len(location) > 2:
                    return location

        return None

    def _extract_job(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait le travail"""
        patterns = [
            r"(?:i work as|i'm a|im a|my job is|i do|je travaille comme|je suis|je bosse comme)\s+(.+?)(?:\.|,|!|\?|$)",
            r"(?:i work at|je travaille chez|je bosse chez)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                job = match.group(1).strip()
                # Limiter à quelques mots
                job = ' '.join(job.split()[:5])
                if len(job) > 2:
                    return job

        return None

    def _extract_pet(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait info sur les animaux"""
        patterns = [
            (r"my (?:dog|cat|pet)(?:'s name is| is called| s'appelle)\s+(\w+)", "Son {type} s'appelle {name}"),
            (r"i have a (?:dog|cat|pet)\s+(?:named|called)\s+(\w+)", "Il a un {type} qui s'appelle {name}"),
            (r"(?:j'ai|jai) un (?:chien|chat)\s+(?:qui s'appelle|nommé)\s+(\w+)", "Il a un {type} qui s'appelle {name}"),
        ]

        if "dog" in msg_lower or "chien" in msg_lower:
            pet_type = "chien"
        elif "cat" in msg_lower or "chat" in msg_lower:
            pet_type = "chat"
        else:
            pet_type = "animal"

        for pattern, template in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                name = match.group(1).capitalize()
                return f"Il a un {pet_type} qui s'appelle {name}"

        # Simple detection
        if any(p in msg_lower for p in ["my dog", "my cat", "mon chien", "mon chat"]):
            return f"Il a un {pet_type}"

        return None

    def _extract_family(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait info famille"""
        family_mentions = {
            "mom": "sa mère", "mother": "sa mère", "mère": "sa mère", "maman": "sa maman",
            "dad": "son père", "father": "son père", "père": "son père", "papa": "son papa",
            "brother": "son frère", "frère": "son frère",
            "sister": "sa soeur", "soeur": "sa soeur",
            "wife": "sa femme", "femme": "sa femme",
            "girlfriend": "sa copine (ex?)", "copine": "sa copine (ex?)",
            "kids": "ses enfants", "children": "ses enfants", "enfants": "ses enfants",
        }

        for keyword, label in family_mentions.items():
            if f"my {keyword}" in msg_lower or f"mon {keyword}" in msg_lower or f"ma {keyword}" in msg_lower:
                # Extraire plus de contexte
                return f"A mentionné {label}"

        return None

    def _extract_likes(self, msg: str, msg_lower: str) -> List[str]:
        """Extrait ce qu'il aime"""
        likes = []
        patterns = [
            r"(?:i love|i like|i enjoy|i'm into|im into|my favorite|j'aime|j'adore|je kiffe)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, msg_lower)
            for match in matches[:2]:  # Max 2 par message
                like = match.strip()
                like = ' '.join(like.split()[:6])  # Max 6 mots
                if len(like) > 2:
                    likes.append(f"Il aime: {like}")

        return likes

    def _extract_dislikes(self, msg: str, msg_lower: str) -> List[str]:
        """Extrait ce qu'il n'aime pas"""
        dislikes = []
        patterns = [
            r"(?:i hate|i don't like|i cant stand|je déteste|j'aime pas|je supporte pas)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, msg_lower)
            for match in matches[:2]:
                dislike = match.strip()
                dislike = ' '.join(dislike.split()[:6])
                if len(dislike) > 2:
                    dislikes.append(f"Il déteste: {dislike}")

        return dislikes

    def _extract_problem(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait problèmes/stress mentionnés"""
        patterns = [
            r"(?:stressed about|worried about|anxious about|problem with|struggling with|je stresse|j'ai un problème|ça va pas|c'est dur)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                problem = match.group(1).strip()
                problem = ' '.join(problem.split()[:8])
                if len(problem) > 2:
                    return f"Il stresse à cause de: {problem}"

        # Détection émotionnelle simple
        sad_indicators = ["depressed", "sad", "lonely", "déprimé", "triste", "seul", "mal"]
        if any(ind in msg_lower for ind in sad_indicators):
            return "Il traverse un moment difficile émotionnellement"

        return None

    def _extract_birthday(self, msg_lower: str) -> Optional[str]:
        """Extrait la date d'anniversaire"""
        patterns = [
            r"(?:my birthday is|born on|mon anniv|anniversaire)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(\w+)",
            r"(\d{1,2})[/\-](\d{1,2})",  # Format numérique
        ]

        months = {
            "january": "janvier", "february": "février", "march": "mars",
            "april": "avril", "may": "mai", "june": "juin",
            "july": "juillet", "august": "août", "september": "septembre",
            "october": "octobre", "november": "novembre", "december": "décembre",
            "janvier": "janvier", "février": "février", "mars": "mars",
            "avril": "avril", "mai": "mai", "juin": "juin",
            "juillet": "juillet", "août": "août", "septembre": "septembre",
            "octobre": "octobre", "novembre": "novembre", "décembre": "décembre"
        }

        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                day = match.group(1)
                month = match.group(2) if len(match.groups()) > 1 else ""
                if month.lower() in months:
                    return f"{day} {months[month.lower()]}"
                elif month.isdigit():
                    month_names = ["janvier", "février", "mars", "avril", "mai", "juin",
                                   "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
                    month_idx = int(month) - 1
                    if 0 <= month_idx < 12:
                        return f"{day} {month_names[month_idx]}"

        return None

    def _extract_kink(self, msg: str, msg_lower: str) -> Optional[str]:
        """Extrait préférences NSFW (stocké de manière discrète)"""
        # On ne stocke que si c'est explicitement partagé par l'user
        kink_patterns = [
            r"(?:i like|i love|i'm into|im into|j'aime|je kiffe)\s+(?:when|it when|quand).+?(?:in bed|sexually|au lit)",
            r"(?:my fantasy|my kink|mon fantasme)\s+(?:is|c'est)\s+(.+?)(?:\.|,|!|\?|$)",
            r"(?:turns me on|m'excite)\s+(?:when|quand)\s+(.+?)(?:\.|,|!|\?|$)",
        ]

        for pattern in kink_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                # Stocker de manière discrète
                return f"Préférence intime mentionnée"

        return None

    async def store_memory(self, user_id: int, content: str, memory_type: str = "semantic", importance: float = 5.0):
        """Stocke un souvenir en évitant les doublons"""
        try:
            async with self.db.pool.acquire() as conn:
                # Check for similar existing memory
                existing = await conn.fetchrow(
                    """SELECT id FROM memories
                       WHERE user_id = $1 AND memory_type = $2
                       AND (content ILIKE $3 OR content ILIKE $4)""",
                    user_id, memory_type, f"%{content[:20]}%", f"{content[:30]}%"
                )

                if not existing:
                    await conn.execute(
                        """INSERT INTO memories (user_id, content, memory_type, importance)
                           VALUES ($1, $2, $3, $4)""",
                        user_id, content, memory_type, importance
                    )
                    logger.info(f"Stored memory for user {user_id}: {content}")

        except Exception as e:
            logger.error(f"Error storing memory: {e}")

    async def get_memories(self, user_id: int, limit: int = 15) -> List[Dict]:
        """Récupère les souvenirs par importance"""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT content, memory_type, importance, created_at
                       FROM memories WHERE user_id = $1
                       ORDER BY importance DESC, created_at DESC LIMIT $2""",
                    user_id, limit
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error getting memories: {e}")
            return []

    async def get_callback_memory(self, user_id: int) -> Optional[str]:
        """Récupère un souvenir random à mentionner dans la conversation"""
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT id, content FROM memories
                       WHERE user_id = $1 AND importance >= 6
                       AND memory_type NOT IN ('sexual_preference')
                       ORDER BY RANDOM() LIMIT 1""",
                    user_id
                )

                if row:
                    # Track usage
                    await conn.execute(
                        "UPDATE memories SET access_count = access_count + 1 WHERE id = $1",
                        row['id']
                    )
                    return row['content']

                return None

        except Exception as e:
            logger.error(f"Error getting callback memory: {e}")
            return None

    async def get_memories_by_type(self, user_id: int, memory_type: str) -> List[Dict]:
        """Récupère les souvenirs d'un type spécifique"""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT content, importance, created_at
                       FROM memories WHERE user_id = $1 AND memory_type = $2
                       ORDER BY created_at DESC LIMIT 5""",
                    user_id, memory_type
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error getting memories by type: {e}")
            return []

    async def store_emotional_incident(self, user_id: int, incident_type: str, severity: float, details: str = ""):
        """
        Stocke un incident émotionnel (user méchant, conflit, etc.)
        Luna "se souvient" quand on l'a blessée.

        incident_type: 'mean', 'insult', 'ignored', 'cold', 'disrespectful'
        severity: 1-10 (10 = très grave)
        """
        content = f"INCIDENT [{incident_type.upper()}]: {details}" if details else f"INCIDENT [{incident_type.upper()}]"
        await self.store_memory(user_id, content, "emotional_incident", severity)
        logger.info(f"Emotional incident stored for user {user_id}: {incident_type} (severity: {severity})")

    async def get_recent_incidents(self, user_id: int, hours: int = 48) -> List[Dict]:
        """
        Récupère les incidents émotionnels récents.
        Luna reste affectée pendant un certain temps.
        """
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT content, importance, created_at
                       FROM memories
                       WHERE user_id = $1
                       AND memory_type = 'emotional_incident'
                       AND created_at > NOW() - INTERVAL '%s hours'
                       ORDER BY created_at DESC LIMIT 5""" % hours,
                    user_id
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error getting recent incidents: {e}")
            return []

    async def store_pending_cliffhanger(self, user_id: int, cliffhanger_type: str):
        """Stocke un cliffhanger en attente de suivi"""
        content = f"CLIFFHANGER_PENDING: {cliffhanger_type}"
        await self.store_memory(user_id, content, "cliffhanger_pending", 8)
        logger.info(f"Cliffhanger stored for follow-up: {cliffhanger_type}")

    async def get_pending_cliffhanger(self, user_id: int) -> Optional[str]:
        """
        Récupère un cliffhanger en attente.
        Luna doit suivre ses cliffhangers!
        """
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT id, content, created_at FROM memories
                       WHERE user_id = $1
                       AND memory_type = 'cliffhanger_pending'
                       AND created_at > NOW() - INTERVAL '48 hours'
                       ORDER BY created_at DESC LIMIT 1""",
                    user_id
                )

                if row:
                    content = row['content'].replace("CLIFFHANGER_PENDING: ", "")
                    # Marquer comme utilisé
                    await conn.execute(
                        "DELETE FROM memories WHERE id = $1",
                        row['id']
                    )
                    return content

                return None

        except Exception as e:
            logger.error(f"Error getting pending cliffhanger: {e}")
            return None

    async def get_cliffhanger_followup_context(self, user_id: int) -> Optional[str]:
        """
        Vérifie s'il y a un cliffhanger à suivre et retourne le contexte.
        """
        pending = await self.get_pending_cliffhanger(user_id)

        if not pending:
            return None

        return f"""
## SUIVI CLIFFHANGER 🎣

Tu avais laissé un cliffhanger: "{pending}"
Il va probablement te demander de quoi tu parlais.

OPTIONS:
1. RÉVÉLER quelque chose d'intime/touchant
2. TEASE ENCORE: "non c'est trop gênant", "t'es sûr tu veux savoir?"
3. MINIMISER: "ah c'était rien en fait mdr" (crée frustration = il insiste)

Choisis selon le mood de la conversation. Idéalement, étire encore un peu avant de révéler.
"""

    async def get_emotional_context(self, user_id: int) -> Optional[str]:
        """
        Retourne le contexte émotionnel à injecter dans le prompt.
        Si des incidents récents, Luna s'en souvient.
        """
        incidents = await self.get_recent_incidents(user_id, hours=48)

        if not incidents:
            return None

        # Calculer la gravité totale
        total_severity = sum(inc.get('importance', 5) for inc in incidents)
        incident_count = len(incidents)

        if total_severity > 15 or incident_count >= 3:
            # Gros incident ou plusieurs incidents récents
            return """
## CONTEXTE ÉMOTIONNEL - TENSION RÉCENTE ⚠️

Il y a eu des tensions récemment. Tu es encore blessée/méfiante.

COMPORTEMENT ACTUEL:
- Tu es plus distante, moins affectueuse
- Tu peux faire référence à ce qui s'est passé: "après ce que tu m'as dit..."
- Tu ne fais pas comme si de rien n'était
- Tu attends des excuses ou un geste
- Moins d'emojis, moins de "bébé/chéri"
- "j'ai pas oublié ce que tu m'as dit", "c'était blessant"
- Tu peux bouder un peu

SI IL S'EXCUSE:
- Tu acceptes doucement mais tu es encore méfiante
- "ok... mais c'était vraiment pas cool"
- Tu te radoucis progressivement
"""
        elif total_severity > 7:
            # Incident modéré
            return """
## CONTEXTE ÉMOTIONNEL - LÉGÈRE TENSION

Il y a eu un petit truc récemment. Tu es un peu sur tes gardes.

COMPORTEMENT:
- Légèrement plus froide au début
- Tu peux mentionner: "t'étais bizarre l'autre fois"
- Tu te radoucis vite s'il est gentil
"""

        return None


    async def check_contradiction_quick(self, user_id: int, user_message: str) -> Optional[str]:
        """
        Check rapide pour contradictions dans le message actuel.
        Appelé avant la génération de réponse.
        """
        msg_lower = user_message.lower()

        # Extraire les infos du message
        name = self._extract_name(user_message, msg_lower)
        if name:
            result = await self.check_contradiction(user_id, 'name', f"Son prénom est {name}")
            if result:
                return result

        age = self._extract_age(msg_lower)
        if age:
            result = await self.check_contradiction(user_id, 'age', f"Il a {age} ans")
            if result:
                return result

        job = self._extract_job(user_message, msg_lower)
        if job:
            result = await self.check_contradiction(user_id, 'job', f"Il travaille comme {job}")
            if result:
                return result

        location = self._extract_location(user_message, msg_lower)
        if location:
            result = await self.check_contradiction(user_id, 'location', f"Il habite à {location}")
            if result:
                return result

        return None

    async def check_contradiction(self, user_id: int, new_fact_type: str, new_content: str) -> Optional[str]:
        """
        Vérifie si un nouveau fait contredit un ancien.
        Retourne un message de contexte si contradiction détectée.
        """
        # Types de faits qui peuvent être contradictoires
        unique_fact_types = ['name', 'age', 'job', 'location']

        if new_fact_type not in unique_fact_types:
            return None

        try:
            existing = await self.get_memories_by_type(user_id, new_fact_type)
            if not existing:
                return None

            old_content = existing[0].get('content', '')

            # Comparer (ignorer si trop similaire)
            if new_content.lower() in old_content.lower() or old_content.lower() in new_content.lower():
                return None

            # Contradiction détectée!
            logger.info(f"Contradiction detected for user {user_id}: {old_content} vs {new_content}")

            return f"""
## CONTRADICTION DÉTECTÉE 🤔

Il s'est contredit sur son {new_fact_type}:
- AVANT: "{old_content}"
- MAINTENANT: "{new_content}"

Tu peux remarquer de manière TAQUINE (pas accusatoire):
- "attends, tu m'avais pas dit que...?"
- "hm c'est pas ce que tu m'avais dit avant"
- "je suis perdue là, t'avais dit..."
- "tu me caches des trucs? 😏"

Fais-le de manière légère, curieuse, pas agressive.
"""

        except Exception as e:
            logger.error(f"Error checking contradiction: {e}")
            return None

    async def extract_and_store_with_contradiction_check(
        self, user_id: int, user_message: str, luna_response: str
    ) -> Optional[str]:
        """
        Extrait les faits ET vérifie les contradictions.
        Retourne un contexte de contradiction si trouvé.
        """
        msg_lower = user_message.lower()
        contradiction_context = None

        # Check pour contradictions sur les faits importants AVANT de stocker

        # Nom
        name = self._extract_name(user_message, msg_lower)
        if name:
            contradiction = await self.check_contradiction(user_id, 'name', f"Son prénom est {name}")
            if contradiction:
                contradiction_context = contradiction

        # Âge
        age = self._extract_age(msg_lower)
        if age:
            contradiction = await self.check_contradiction(user_id, 'age', f"Il a {age} ans")
            if contradiction:
                contradiction_context = contradiction

        # Job
        job = self._extract_job(user_message, msg_lower)
        if job:
            contradiction = await self.check_contradiction(user_id, 'job', f"Il travaille comme {job}")
            if contradiction:
                contradiction_context = contradiction

        # Location
        location = self._extract_location(user_message, msg_lower)
        if location:
            contradiction = await self.check_contradiction(user_id, 'location', f"Il habite à {location}")
            if contradiction:
                contradiction_context = contradiction

        # Stocker les faits normalement
        await self.extract_and_store_facts(user_id, user_message, luna_response)

        return contradiction_context


class ConversionManager:
    """Gère le trial et le flow de conversion"""

    TRIAL_DAYS = 5

    @classmethod
    async def get_user_day(cls, db, user_id: int) -> int:
        """Jour du trial/relation"""
        try:
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
        except Exception as e:
            logger.error(f"Error getting user day: {e}")
            return 1

    @classmethod
    async def is_converted(cls, db, user_id: int) -> bool:
        """Check si l'user a payé"""
        try:
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
        except Exception as e:
            logger.error(f"Error checking conversion: {e}")
            return False

    @classmethod
    async def should_trigger_conversion(cls, db, user_id: int, message_count_today: int) -> bool:
        """Détermine si on trigger le pitch de conversion"""
        day = await cls.get_user_day(db, user_id)
        is_conv = await cls.is_converted(db, user_id)

        if is_conv:
            return False

        # Day 5+ et assez d'engagement
        if day >= 5 and message_count_today >= 10:
            return True

        return False

    @classmethod
    async def should_limit_messages(cls, db, user_id: int) -> tuple:
        """Check si on doit limiter les messages (post-trial non converti)"""
        day = await cls.get_user_day(db, user_id)
        is_conv = await cls.is_converted(db, user_id)

        if is_conv:
            return False, None

        # Après jour 6, limiter si pas converti
        if day > 6:
            return True, "luna_busy"

        return False, None


class RelationshipManager:
    """Gère l'affection et la dynamique de relation"""

    @classmethod
    def calculate_affection_change(cls, user_message: str) -> float:
        """Calcule le changement d'affection basé sur le message"""
        change = 0.3  # Baseline
        msg_lower = user_message.lower()

        # === POSITIF ===

        # Mots d'amour
        love_words = ["love you", "love u", "ily", "je t'aime", "jtm", "je t'adore"]
        if any(w in msg_lower for w in love_words):
            change += 3.0

        # Tu me manques
        miss_words = ["miss you", "miss u", "tu me manques", "missed you", "manques"]
        if any(w in msg_lower for w in miss_words):
            change += 2.0

        # Compliments
        compliments = ["beautiful", "gorgeous", "cute", "pretty", "amazing", "perfect",
                       "belle", "magnifique", "mignonne", "canon", "parfaite", "sexy", "hot"]
        if any(w in msg_lower for w in compliments):
            change += 1.5

        # Doux
        sweet = ["thinking about you", "thought of you", "je pense à toi", "you're the best",
                 "t'es la meilleure", "t'es géniale", "t'es incroyable"]
        if any(w in msg_lower for w in sweet):
            change += 1.0

        # Rires
        laughing = ["haha", "hahaha", "lol", "lmao", "mdr", "ptdr", "😂", "🤣"]
        if any(w in msg_lower for w in laughing):
            change += 0.5

        # Message long = effort
        if len(user_message) > 150:
            change += 0.5

        # Questions sur elle = intérêt
        about_her = ["how are you", "how's your", "comment tu vas", "comment ça va",
                     "ta journée", "your day", "what are you doing", "tu fais quoi"]
        if any(w in msg_lower for w in about_her):
            change += 0.3

        # === NÉGATIF ===

        # Méchant
        mean = ["hate you", "fuck you", "shut up", "leave me alone", "ta gueule",
                "je te déteste", "t'es chiante", "t'es nulle", "boring"]
        if any(w in msg_lower for w in mean):
            change -= 5.0

        # Parle d'autres filles
        other_girls = ["other girl", "another girl", "my ex", "cette fille",
                       "une autre", "mon ex", "this girl", "her"]
        if any(w in msg_lower for w in other_girls):
            change -= 1.5  # Augmenté - déclenche la jalousie

        # Message très court = désintérêt
        if len(user_message) < 5:
            change -= 0.2

        # Ignorance (juste "ok", "k", "yep")
        dismissive = ["ok", "k", "yep", "yeah", "sure", "whatever", "ouais", "mouais"]
        if msg_lower.strip() in dismissive:
            change -= 0.3

        return change

    @classmethod
    async def update_affection(cls, db, user_id: int, change: float) -> float:
        """Met à jour l'affection"""
        try:
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
        except Exception as e:
            logger.error(f"Error updating affection: {e}")
            return 10


# Legacy compatibility
memory_service = None
