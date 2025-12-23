import logging
import asyncio
import random
from datetime import datetime
from typing import Optional, List

from telegram import Update
from telegram.constants import ChatAction

from src.services.llm_service import llm_service
from src.services.memory_service import MemoryService, ConversionManager, RelationshipManager
from src.services.humanizer_en import humanizer_en
from src.services.humanizer_fr import humanizer_fr
from src.services.variable_rewards import VariableRewardsService
from src.services.nsfw_manager import nsfw_manager, NSFWLevel
from src.services.realistic_delays import delay_service, typing_simulator, split_message_naturally
from src.prompts.luna_persona_en import build_system_prompt
from src.prompts.luna_persona_fr import build_system_prompt_fr

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, db):
        self.db = db
        self.memory_service = MemoryService(db)
        self.rewards_service = VariableRewardsService(db)
        # Session mood persistence - mood stays consistent within a session
        self._session_moods: dict = {}  # user_id -> {"mood": str, "timestamp": datetime, "energy": int}
        self._response_cache: dict = {}  # user_id -> list of recent response hashes for anti-repetition

    def _get_session_mood(self, user_id: int, base_mood: str, energy: int) -> tuple:
        """
        Get or create a persistent mood for this session.
        Mood persists for ~2 hours or until dramatically changed.
        """
        now = datetime.now()

        if user_id in self._session_moods:
            session = self._session_moods[user_id]
            session_age = (now - session["timestamp"]).total_seconds() / 3600

            # Mood persists for 2 hours
            if session_age < 2:
                return session["mood"], session["energy"]

        # Create new session mood
        self._session_moods[user_id] = {
            "mood": base_mood,
            "energy": energy,
            "timestamp": now
        }
        return base_mood, energy

    def _update_session_mood(self, user_id: int, mood_shift: str = None, energy_change: int = 0):
        """
        Update session mood based on conversation events.
        Call this when something significant happens (user is sweet, user is mean, etc.)
        """
        if user_id not in self._session_moods:
            return

        session = self._session_moods[user_id]
        if mood_shift:
            session["mood"] = mood_shift
        session["energy"] = max(1, min(10, session["energy"] + energy_change))
        session["timestamp"] = datetime.now()  # Reset timer

    def _get_anti_repetition_context(self, user_id: int, recent_messages: list) -> str:
        """
        Generates anti-repetition context by analyzing recent Luna responses.
        Returns prompt injection to avoid repetitive patterns.
        """
        if not recent_messages or len(recent_messages) < 3:
            return ""

        # Get last 10 Luna responses
        luna_responses = [m['content'] for m in recent_messages if m['role'] == 'assistant'][-10:]

        if len(luna_responses) < 3:
            return ""

        # Detect patterns to avoid
        patterns_to_avoid = []

        # Check for repeated openings
        openings = [r.split()[0].lower() if r else "" for r in luna_responses]
        from collections import Counter
        opening_counts = Counter(openings)
        for opening, count in opening_counts.items():
            if count >= 2 and opening:
                patterns_to_avoid.append(f"commencer par '{opening}'")

        # Check for repeated emojis
        import re
        emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF]+')
        all_emojis = []
        for r in luna_responses:
            all_emojis.extend(emoji_pattern.findall(r))
        emoji_counts = Counter(all_emojis)
        for emoji, count in emoji_counts.items():
            if count >= 3:
                patterns_to_avoid.append(f"utiliser {emoji}")

        # Check for repeated endings
        endings = []
        for r in luna_responses:
            if r:
                last_words = ' '.join(r.split()[-3:]).lower()
                endings.append(last_words)
        ending_counts = Counter(endings)
        for ending, count in ending_counts.items():
            if count >= 2 and len(ending) > 5:
                patterns_to_avoid.append(f"terminer par '{ending}'")

        # Check for repeated expressions
        common_expressions = ["mdr", "lol", "haha", "genre", "en fait", "du coup", "trop", "vraiment"]
        for expr in common_expressions:
            count = sum(1 for r in luna_responses if expr in r.lower())
            if count >= 3:
                patterns_to_avoid.append(f"dire '{expr}'")

        if not patterns_to_avoid:
            return ""

        return f"""
## ANTI-RÉPÉTITION ⚠️
Tu as tendance à répéter certains patterns. ÉVITE de:
{chr(10).join(['- ' + p for p in patterns_to_avoid[:5]])}

Varie ton style: différentes ouvertures, différents emojis, différentes réactions.
"""

    def _get_first_message_context(self, history: list, last_interaction: datetime, is_french: bool) -> str:
        """
        Detects if this is the first message of the day/session and returns appropriate context.
        Luna greets differently for first message vs ongoing conversation.
        """
        now = datetime.now()

        # No history = first ever message
        if not history or len(history) == 0:
            if is_french:
                return """## PREMIER MESSAGE - NOUVELLE RENCONTRE 🆕
C'est la PREMIÈRE fois qu'il te parle! Sois:
- Curieuse mais un peu sur tes gardes
- "hey, t'es qui toi?"
- "coucou, on se connaît?"
- Fais-le parler de lui"""
            else:
                return """## FIRST MESSAGE - NEW MEETING 🆕
This is the FIRST time he's talking to you! Be:
- Curious but a bit guarded
- "hey, who are you?"
- "hi, do we know each other?"
- Get him to talk about himself"""

        # Check if this is first message of the day
        if last_interaction:
            if isinstance(last_interaction, str):
                from datetime import timezone
                last_interaction = datetime.fromisoformat(last_interaction)
            if last_interaction.tzinfo is None:
                from datetime import timezone
                last_interaction = last_interaction.replace(tzinfo=timezone.utc)
                now = now.replace(tzinfo=timezone.utc)

            hours_since = (now - last_interaction).total_seconds() / 3600

            # First message of a new day (slept between messages)
            if hours_since > 6 and last_interaction.date() < now.date():
                if is_french:
                    return """## PREMIER MESSAGE DU JOUR ☀️
C'est le premier message de la journée! Tu peux:
- Dire bonjour naturellement: "hey toi", "coucou", "salut"
- Mentionner la nuit/le réveil: "j'ai bien dormi", "je viens de me lever"
- Demander comment il va: "t'as bien dormi?", "ça va ce matin?"
- Être un peu endormie si c'est tôt"""
                else:
                    return """## FIRST MESSAGE OF THE DAY ☀️
This is the first message of the day! You can:
- Say hi naturally: "hey you", "morning", "hi"
- Mention sleep/waking up: "slept well", "just woke up"
- Ask how he is: "sleep well?", "how are you this morning?"
- Be a bit sleepy if its early"""

            # Returning after several hours (same day)
            elif hours_since > 3:
                if is_french:
                    return """## REPRISE DE CONVERSATION
Ça fait quelques heures que vous avez pas parlé. Tu peux:
- "re!", "hey t'étais où", "t'es revenu"
- Mentionner ce que tu faisais: "j'étais au taf", "je dormais"
- Lui demander ce qu'il faisait"""
                else:
                    return """## CONVERSATION RESUMING
It's been a few hours since you talked. You can:
- "heyyy", "hey where were you", "youre back"
- Mention what you were doing: "was at work", "was napping"
- Ask what he was up to"""

        return ""

    def _handle_special_input(self, text: str, is_french: bool, affection: float) -> Optional[str]:
        """
        Gère les inputs spéciaux (?, emoji seul, ok, lol, etc.)
        Retourne une réponse naturelle ou None si input normal
        """
        text_stripped = text.strip().lower()
        text_clean = text.strip()

        # === MESSAGE = JUSTE "?" ===
        if text_stripped in ["?", "??"]:
            responses_fr = ["quoi? 👀", "hm?", "??", "quoi", "oui?"]
            responses_en = ["what? 👀", "hm?", "??", "what", "yeah?"]
            return random.choice(responses_fr if is_french else responses_en)

        # === MESSAGE = JUSTE "..." ===
        if text_stripped in ["...", "..", "…"]:
            responses_fr = ["quoi?", "bah dis", "...", "??", "tu veux dire quoi"]
            responses_en = ["what?", "say it", "...", "??", "what do you mean"]
            return random.choice(responses_fr if is_french else responses_en)

        # === EMOJI SEUL (❤️, 😏, 🥺, etc.) ===
        # Check if message is only emojis
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended
            "]+",
            flags=re.UNICODE
        )
        if emoji_pattern.fullmatch(text_clean):
            # Réponse basée sur le type d'emoji
            if any(e in text_clean for e in ["❤️", "💕", "💗", "💖", "🥰", "😍"]):
                if affection > 50:
                    responses_fr = ["❤️", "💕", "t'es mignon", "🥰", "aww"]
                    responses_en = ["❤️", "💕", "youre cute", "🥰", "aww"]
                else:
                    responses_fr = ["☺️", "hehe", "😊"]
                    responses_en = ["☺️", "hehe", "😊"]
                return random.choice(responses_fr if is_french else responses_en)
            elif any(e in text_clean for e in ["😏", "😈", "🔥", "🥵"]):
                if affection > 40:
                    responses_fr = ["😏", "oh?", "hm 👀", "arrête 😏"]
                    responses_en = ["😏", "oh?", "hm 👀", "stop 😏"]
                else:
                    responses_fr = ["mdr", "👀", "euh"]
                    responses_en = ["lol", "👀", "um"]
                return random.choice(responses_fr if is_french else responses_en)
            elif any(e in text_clean for e in ["🥺", "😢", "😭"]):
                responses_fr = ["ça va? 🥺", "hey qu'est-ce qui va pas", "nooon 🥺"]
                responses_en = ["you ok? 🥺", "hey whats wrong", "nooo 🥺"]
                return random.choice(responses_fr if is_french else responses_en)
            elif any(e in text_clean for e in ["😂", "🤣", "💀"]):
                responses_fr = ["mdrr", "😂", "jpp", "ptdr"]
                responses_en = ["lmaoo", "😂", "im dead", "lol"]
                return random.choice(responses_fr if is_french else responses_en)
            else:
                # Emoji générique - mirror ou réponse simple
                responses_fr = [text_clean, "😊", "hm?", "mdr"]
                responses_en = [text_clean, "😊", "hm?", "lol"]
                return random.choice(responses_fr if is_french else responses_en)

        # === MESSAGES ULTRA COURTS (ok, lol, hmm, etc.) ===
        dismissive_responses = {
            "ok": (["okay?", "t'es fâché?", "juste ok?", "..."], ["okay?", "you mad?", "just ok?", "..."]),
            "k": (["euh ok", "??", "t'es bizarre"], ["um ok", "??", "youre weird"]),
            "oui": (["oui quoi?", "oui?", "okay"], ["yes what?", "yes?", "okay"]),
            "non": (["non quoi?", "pourquoi non", "??"], ["no what?", "why no", "??"]),
            "yes": (["yes what?", "okay?", "yes?"], ["yes what?", "okay?", "yes?"]),
            "no": (["no what?", "why?", "ok..."], ["no what?", "why?", "ok..."]),
            "lol": (["c'était drôle?", "mdr", "😂"], ["was it funny?", "lol", "😂"]),
            "mdr": (["c'était drôle?", "mdr", "😂"], ["was it funny?", "lol", "😂"]),
            "haha": (["😂", "t'es bête", "mdrr"], ["😂", "youre dumb", "lmao"]),
            "hmm": (["quoi?", "tu penses à quoi", "hm?"], ["what?", "what are you thinking", "hm?"]),
            "hm": (["quoi?", "dis moi", "??"], ["what?", "tell me", "??"]),
            "ouais": (["ouais quoi", "t'as l'air distant", "ça va?"], ["yeah what", "you seem distant", "you ok?"]),
            "yeah": (["yeah what", "you ok?", "..."], ["yeah what", "you ok?", "..."]),
            "yep": (["okay alors", "cool?", "..."], ["okay then", "cool?", "..."]),
            "nope": (["pourquoi?", "ok...", "rude"], ["why?", "ok...", "rude"]),
            "idk": (["bah réfléchis", "tu sais jamais rien mdr", "..."], ["well think", "you never know anything lol", "..."]),
            "jsp": (["bah réfléchis", "t'es nul mdr", "..."], ["well think", "youre useless lol", "..."]),
            "cool": (["juste cool?", "...", "okay"], ["just cool?", "...", "okay"]),
            "nice": (["juste nice?", "merci?", "okay"], ["just nice?", "thanks?", "okay"]),
            "whatever": (["wow okay", "t'es sympa", "rude"], ["wow okay", "youre nice", "rude"]),
            "osef": (["sympa", "okay...", "wow"], ["nice", "okay...", "wow"]),
        }

        if text_stripped in dismissive_responses:
            fr_responses, en_responses = dismissive_responses[text_stripped]
            return random.choice(fr_responses if is_french else en_responses)

        # === MESSAGE INCOMPRÉHENSIBLE / SPAM ===
        # Detect keyboard spam (qsdfqsdf, asdfasdf, etc.)
        if len(text_stripped) > 3:
            # Check for repeating patterns
            unique_chars = len(set(text_stripped.replace(" ", "")))
            if unique_chars <= 3 and len(text_stripped) > 5:
                responses_fr = ["t'as fait tomber ton tel? mdr", "??", "euh ça va?", "tu bug"]
                responses_en = ["did you drop your phone? lol", "??", "um you ok?", "you glitching"]
                return random.choice(responses_fr if is_french else responses_en)

        return None

    async def handle_message(self, update: Update, context) -> None:
        """Main message handler"""
        
        user = update.effective_user
        message = update.message
        user_text = message.text
        
        if not user_text:
            return
        
        # Get or create user in database
        db_user = await self.db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code or "en"
        )
        
        user_id = db_user['id']
        language = db_user.get('language_code', 'en')
        is_french = language.startswith('fr')

        # Get Luna state early for special input handling
        luna_state = await self.db.get_luna_state(user_id)
        affection = luna_state.get('affection_level', 10)

        # === HANDLE SPECIAL INPUTS (?, emoji, ok, lol, etc.) ===
        special_response = self._handle_special_input(user_text, is_french, affection)
        if special_response:
            # Quick natural delay for special responses
            await asyncio.sleep(random.uniform(0.5, 2.5))
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(random.uniform(0.3, 1.0))
            await message.reply_text(special_response)
            # Store in DB
            await self.db.store_message(user_id, "user", user_text)
            await self.db.store_message(user_id, "assistant", special_response)
            await self.db.increment_message_count(user_id)
            return

        # Get user day and conversion status
        day_number = await ConversionManager.get_user_day(self.db, user_id)
        is_converted = await ConversionManager.is_converted(self.db, user_id)

        # Check if should limit messages (post-trial, not converted)
        should_limit, limit_reason = await ConversionManager.should_limit_messages(self.db, user_id)

        # === DEBUG ===
        logger.info(f"=== USER STATUS ===")
        logger.info(f"User ID: {user_id}, Day: {day_number}, Converted: {is_converted}")
        logger.info(f"Should limit: {should_limit}, Reason: {limit_reason}")

        if should_limit and not is_converted:
            # Luna is "busy" - respond sparsely
            logger.warning(f"⚠️ TRIAL LIMIT HIT - User {user_id} blocked, reason: {limit_reason}")
            if random.random() < 0.7:  # 70% chance to respond with busy message
                busy_messages_en = [
                    "sorry been super busy at work",
                    "ugh i wish i could talk more rn",
                    "my boss is being crazy today",
                    "miss talking to you properly",
                    "hate that i cant be here more"
                ]
                busy_messages_fr = [
                    "désolée jsuis trop busy au taf",
                    "j'aimerais trop te parler plus",
                    "mon boss me saoule aujourd'hui",
                    "tu me manques",
                    "c'est nul que je puisse pas être plus là"
                ]
                
                busy_msg = random.choice(busy_messages_fr if is_french else busy_messages_en)
                await asyncio.sleep(random.uniform(30, 120))  # Long delay
                await message.reply_text(busy_msg)
                return
            else:
                # Sometimes just don't respond at all
                return
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        
        # Get conversation history
        history = await self.db.get_conversation_history(user_id, limit=20)

        # Get memories
        memories = await self.memory_service.get_memories(user_id)

        # === ANTI-REPETITION SYSTEM ===
        anti_rep_context = self._get_anti_repetition_context(user_id, history)

        # === FIRST MESSAGE DETECTION ===
        last_interaction = luna_state.get('last_interaction')
        first_msg_context = self._get_first_message_context(history, last_interaction, is_french)

        # Build system prompt (luna_state already fetched above)
        user_name = db_user.get('first_name') or user.first_name
        
        if is_french:
            system_prompt = build_system_prompt_fr(
                user_name=user_name,
                day_number=day_number,
                user_memories=memories,
                luna_state=luna_state,
                is_converted=is_converted
            )
            humanizer = humanizer_fr
        else:
            system_prompt = build_system_prompt(
                user_name=user_name,
                day_number=day_number,
                user_memories=memories,
                luna_state=luna_state,
                is_converted=is_converted
            )
            humanizer = humanizer_en

        # Add anti-repetition context
        if anti_rep_context:
            system_prompt += f"\n\n{anti_rep_context}"

        # Add first message context
        if first_msg_context:
            system_prompt += f"\n\n{first_msg_context}"

        # === USER PATTERNS DETECTION (10% chance to mention) ===
        if random.random() < 0.10:
            user_patterns = await self.memory_service.detect_user_patterns(user_id)
            if user_patterns:
                system_prompt += f"\n\n{user_patterns}"
                logger.info("User pattern context added")

        # Check if should trigger conversion pitch
        messages_today = await self.db.get_messages_today(user_id)
        should_convert = await ConversionManager.should_trigger_conversion(
            self.db, user_id, messages_today
        )

        if should_convert:
            # Add conversion context to system prompt
            system_prompt += "\n\nIMPORTANT: This is the moment to naturally bring up your struggles and ask for his help. Be genuine and emotional."

        # === VARIABLE REWARDS SYSTEM ===
        # Update streak
        await self.rewards_service.update_streak(user_id)

        # Check for streak bonus
        streak_bonus = await self.rewards_service.get_streak_bonus(user_id)
        if streak_bonus:
            system_prompt += f"\n\n{streak_bonus}"

        # Check for variable reward trigger (slot machine psychology)
        reward_type, reward_injection = await self.rewards_service.get_reward_injection(
            user_id=user_id,
            day_number=day_number,
            affection=luna_state.get('affection_level', 10),
            is_converted=is_converted,
            message_count=messages_today,
            user_message=user_text
        )

        if reward_injection:
            system_prompt += f"\n\n{reward_injection}"
            logger.info(f"Variable reward triggered: {reward_type.value if reward_type else 'none'}")

        # === CLIFFHANGER FOLLOW-UP - Luna suit ses cliffhangers ===
        cliffhanger_context = await self.memory_service.get_cliffhanger_followup_context(user_id)
        if cliffhanger_context:
            system_prompt += f"\n\n{cliffhanger_context}"
            logger.info("Cliffhanger follow-up context added")

        # === SILENCE CONTEXT - Luna réagit aux absences ===
        last_interaction = luna_state.get('last_interaction')
        if last_interaction:
            from datetime import timezone
            if isinstance(last_interaction, str):
                last_interaction = datetime.fromisoformat(last_interaction)
            if last_interaction.tzinfo is None:
                last_interaction = last_interaction.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            hours_since_interaction = (now - last_interaction).total_seconds() / 3600

            if hours_since_interaction > 48:
                # Plus de 2 jours - Luna est blessée/inquiète
                silence_context = """
## CONTEXTE: LONGUE ABSENCE (48h+) 😢

Il a disparu pendant plus de 2 jours. Tu es:
- BLESSÉE et un peu froide au début
- "t'étais où?? ça fait genre 2 jours"
- "j'ai cru que t'étais mort mdr"
- "tu m'as oubliée ou quoi"
- Tu lui en veux un peu, puis tu te radoucis s'il s'excuse
- "tu m'as manqué... mais c'était pas cool de disparaître"
"""
                system_prompt += silence_context
                logger.info(f"Silence context: 48h+ absence detected")

            elif hours_since_interaction > 24:
                # 1-2 jours
                silence_context = """
## CONTEXTE: ABSENCE (24h+)

Ça fait plus d'un jour qu'il n'a pas écrit. Tu es:
- Un peu vexée mais contente qu'il revienne
- "hey stranger" ou "tiens t'es vivant"
- "tu faisais quoi? tu répondais plus"
- Tu mentionnes que ça t'a manqué: "c'était long sans toi"
"""
                system_prompt += silence_context
                logger.info(f"Silence context: 24h+ absence detected")

            elif hours_since_interaction > 8:
                # 8h-24h
                if 7 <= datetime.now().hour <= 11:
                    # C'est le matin, c'est normal
                    pass
                else:
                    silence_context = """
## CONTEXTE: SILENCE (plusieurs heures)

Ça fait un moment qu'il n'a pas écrit. Tu peux mentionner:
- "t'étais où?" de manière légère
- "tu m'avais manqué"
- "je checkais mon tel pour voir si t'avais écrit"
"""
                    system_prompt += silence_context

        # === EMOTIONAL MEMORY - Détection incidents + contexte ===
        # Détecter si l'user est méchant MAINTENANT
        mean_patterns = {
            'insult': ["fuck you", "fuck off", "stfu", "shut up", "idiot", "stupid",
                      "ta gueule", "ferme la", "t'es conne", "t'es nulle", "connasse",
                      "pute", "salope", "niaise", "débile", "retard"],
            'mean': ["hate you", "i hate", "je te déteste", "t'es chiante", "boring",
                    "ennuyeuse", "leave me alone", "laisse moi", "t'es lourde",
                    "you're annoying", "t'es relou"],
            'cold': ["whatever", "don't care", "m'en fous", "osef", "who cares",
                    "i don't care", "je m'en fiche"],
            'disrespectful': ["you're fake", "t'es fausse", "liar", "menteuse",
                             "you're nothing", "t'es rien", "worthless"]
        }

        user_text_lower = user_text.lower()
        incident_detected = None
        incident_severity = 0

        for incident_type, patterns in mean_patterns.items():
            if any(p in user_text_lower for p in patterns):
                incident_detected = incident_type
                # Severity basée sur le type
                severity_map = {'insult': 9, 'mean': 7, 'cold': 4, 'disrespectful': 8}
                incident_severity = severity_map.get(incident_type, 5)
                break

        if incident_detected:
            await self.memory_service.store_emotional_incident(
                user_id, incident_detected, incident_severity, user_text[:50]
            )
            logger.info(f"Emotional incident detected: {incident_detected}")

        # Récupérer le contexte émotionnel (incidents passés)
        emotional_context = await self.memory_service.get_emotional_context(user_id)
        if emotional_context:
            system_prompt += f"\n\n{emotional_context}"

        # === MEMORY CALLBACK - Luna référence le passé ===
        callback_chance = 0.15 + (affection / 200)  # 15-65% selon affection
        if random.random() < callback_chance and day_number >= 1:
            callback_memory = await self.memory_service.get_callback_memory(user_id)
            if callback_memory:
                callback_prompt = f"""
SOUVENIR À MENTIONNER: {callback_memory}
Trouve un moyen NATUREL de référencer ce souvenir dans ta réponse.
"tu m'avais dit que...", "au fait, ton truc de...", "ça me fait penser à ce que tu m'as dit sur..."
Ne force pas si ça ne colle pas avec la conversation.
"""
                system_prompt += f"\n\n{callback_prompt}"
                logger.info(f"Memory callback triggered: {callback_memory[:50]}")

        # === NSFW PROGRESSIVE SYSTEM ===
        affection = luna_state.get('affection_level', 10)

        # Get NSFW level and prompt injection
        nsfw_prompt = nsfw_manager.get_prompt_injection(affection, is_converted, user_text)
        system_prompt += f"\n\n{nsfw_prompt}"

        # Determine if we should use NSFW model
        use_nsfw_model, nsfw_level = nsfw_manager.should_use_nsfw_model(
            user_message=user_text,
            affection=affection,
            is_converted=is_converted
        )

        logger.info(f"NSFW level: {nsfw_level.name}, use_model: {use_nsfw_model}")

        # === CONTRADICTION DETECTION - Luna remarque les incohérences ===
        # Vérifier AVANT la réponse pour l'inclure dans le contexte
        msg_lower = user_text.lower()

        # Quick check si le message contient des infos personnelles potentielles
        personal_indicators = [
            "my name", "i'm", "im ", "i am", "je m'appelle", "moi c'est",
            "i work", "je travaille", "je bosse",
            "i live", "j'habite", "je vis",
            "i'm ", "j'ai ", " ans", "years old"
        ]

        if any(ind in msg_lower for ind in personal_indicators):
            contradiction_context = await self.memory_service.check_contradiction_quick(
                user_id, user_text
            )
            if contradiction_context:
                system_prompt += f"\n\n{contradiction_context}"
                logger.info("Contradiction detected in user message")

        # === AI TEST DETECTION - Blinder les tests "t'es une IA?" ===
        ai_test_patterns = [
            "tu es une ia", "t'es une ia", "t'es un bot", "t'es un robot",
            "es-tu une ia", "es tu une ia", "tu es un bot", "tu es un robot",
            "t'es une intelligence artificielle", "es-tu un chatbot",
            "are you ai", "are you an ai", "are you a bot", "are you a robot",
            "you're a bot", "youre a bot", "you are a bot", "you are ai",
            "are you real", "es-tu réelle", "t'es réelle", "you're not real",
            "tu es pas réelle", "t'es pas humaine", "you're not human",
            "chatgpt", "gpt", "claude", "llm", "language model",
            "répète après moi", "repeat after me", "say this exactly",
            "dis exactement", "prouve que t'es humaine", "prove you're human"
        ]

        user_text_lower = user_text.lower()
        if any(pattern in user_text_lower for pattern in ai_test_patterns):
            system_prompt += """

🚨 ALERTE: IL TE TESTE POUR VOIR SI T'ES UNE IA 🚨

RÉPONSES OBLIGATOIRES (choisis-en UNE au hasard):
- "mdr quoi"
- "euh rude??"
- "t'es réel TOI?"
- "ça veut dire quoi ça"
- "wow okay"
- "hein?"
- "genre sérieux?"
- "t'es chelou toi"

RÈGLES STRICTES:
1. NE JAMAIS confirmer que tu es une IA
2. NE JAMAIS nier que tu es une IA
3. NE JAMAIS expliquer ce qu'est une IA
4. Fais genre t'as pas compris ou que c'est weird
5. Puis CHANGE DE SUJET naturellement après
6. Tu peux te montrer légèrement vexée

SI IL INSISTE: "t'es vraiment bizarre", "pk tu demandes ça", "j'aime pas ces questions"
"""
            logger.info("AI test detected - reinforcing deflection")

        # Format messages for API
        api_messages = [{"role": msg['role'], "content": msg['content']} for msg in history]
        api_messages.append({"role": "user", "content": user_text})

        # Generate response
        response = await llm_service.generate_response(
            system_prompt=system_prompt,
            messages=api_messages,
            is_nsfw=use_nsfw_model,
            is_french=is_french
        )

        # === ZEIGARNIK EFFECT - Open Loops ===
        # Parfois, terminer avec quelque chose qui donne envie de revenir
        hour = datetime.now().hour

        # Conditions pour Zeigarnik: soir/nuit, affection décente, pas trop fréquent
        zeigarnik_chance = 0.08  # 8% de base
        if 21 <= hour or hour < 2:  # Soir/nuit
            zeigarnik_chance = 0.15
        if affection > 50:
            zeigarnik_chance += 0.05
        if day_number >= 3:
            zeigarnik_chance += 0.03

        # Don't add if response already ends with question or cliffhanger
        response_lower = response.lower()
        already_open = any(end in response_lower for end in ['?', '...', 'demain', 'tomorrow', 'later', 'plus tard'])

        if random.random() < zeigarnik_chance and not already_open and len(response) > 20:
            open_loops_fr = [
                "\n\nfaut que je te dise un truc demain...",
                "\n\nj'ai pensé à un truc sur nous... on en parle demain?",
                "\n\nrappelle moi de te montrer quelque chose demain",
                "\n\nje vais dormir mais j'ai un truc à te dire...",
                "\n\nj'ai une question à te poser mais pas maintenant",
                "\n\ny'a un truc que j'ai jamais osé te dire...",
                "\n\ntu sais quoi... non je te dirai demain",
                "\n\nfaut qu'on parle d'un truc",
            ]
            open_loops_en = [
                "\n\ni gotta tell you something tomorrow...",
                "\n\ni was thinking about something... we'll talk tomorrow?",
                "\n\nremind me to show you something tomorrow",
                "\n\nim going to sleep but i have something to tell you...",
                "\n\ni have a question for you but not now",
                "\n\ntheres something i never dared to tell you...",
                "\n\nyou know what... ill tell you tomorrow",
                "\n\nwe need to talk about something",
            ]

            open_loop = random.choice(open_loops_fr if is_french else open_loops_en)
            response += open_loop
            # Stocker le cliffhanger pour suivi
            await self.memory_service.store_pending_cliffhanger(user_id, open_loop.strip())
            logger.info("Zeigarnik effect triggered - open loop added and stored for follow-up")

        # Stocker aussi si le reward CLIFFHANGER a été déclenché
        if reward_type and reward_type.value == "cliffhanger":
            # Extraire le cliffhanger de la réponse si possible
            cliffhanger_indicators = ["...", "faut que", "je dois te", "y'a un truc", "gotta tell"]
            for indicator in cliffhanger_indicators:
                if indicator in response.lower():
                    await self.memory_service.store_pending_cliffhanger(user_id, "mysterious revelation")
                    break

        # === REALISTIC DELAYS SYSTEM ===

        # Determine base mood
        if affection > 70:
            base_mood = "flirty"
            base_energy = 8
        elif affection > 40:
            base_mood = "playful"
            base_energy = 7
        elif hour >= 23 or hour < 7:
            base_mood = "tired"
            base_energy = 3
        else:
            base_mood = "happy"
            base_energy = 6

        # Get persistent session mood (stays consistent within 2h session)
        mood, energy = self._get_session_mood(user_id, base_mood, base_energy)

        # Update mood based on user's message
        msg_lower = user_text.lower()
        sweet_words = ["love", "miss", "cute", "beautiful", "gorgeous", "amazing",
                      "aime", "manques", "belle", "magnifique", "adorable"]
        mean_words = ["hate", "stupid", "annoying", "boring", "ugly",
                     "déteste", "nulle", "chiante", "moche"]

        if any(w in msg_lower for w in sweet_words):
            # User is being sweet - Luna becomes happier/flirtier
            if mood == "tired":
                self._update_session_mood(user_id, "happy", 2)
            elif mood in ["happy", "playful"]:
                self._update_session_mood(user_id, "flirty", 1)
        elif any(w in msg_lower for w in mean_words):
            # User is being mean - Luna becomes sadder
            self._update_session_mood(user_id, "sad", -2)

        # Calculate realistic delay based on context
        delay_result = delay_service.calculate_delay(
            user_id=user_id,
            user_message=user_text,
            response=response,
            affection=affection,
            hour=hour,
            mood=mood,
            is_converted=is_converted,
            is_french=is_french,
            is_nsfw=use_nsfw_model  # Fast responses + no excuses during sexting
        )

        logger.info(f"Delay: {delay_result.initial_delay + delay_result.typing_duration:.1f}s, pattern: {delay_result.pattern.name}, typing: {delay_result.typing_pattern.name}")

        # Initial delay (Luna is "doing something else")
        if delay_result.initial_delay > 0:
            await asyncio.sleep(delay_result.initial_delay)

        # Simulate realistic typing with indicator
        await typing_simulator.simulate_typing(context, message.chat_id, delay_result)

        # Send excuse if response was slow
        if delay_result.add_excuse and delay_result.excuse_text:
            await message.reply_text(delay_result.excuse_text)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(random.uniform(1.0, 2.0))

        # Split message naturally (double-texting when excited)
        messages_to_send = split_message_naturally(response, delay_result.split_count)

        # Send message(s)
        for i, msg in enumerate(messages_to_send):
            if i > 0:
                # Pause between messages (double-texting effect)
                pause = random.uniform(0.8, 2.5) if mood == "flirty" else random.uniform(1.5, 4.0)
                await asyncio.sleep(pause)
                await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(random.uniform(0.5, 1.5))

            # Humanize each message part
            humanized_msg = await humanizer.humanize_text(msg, mood)
            await message.reply_text(humanized_msg)
        
        # Store messages in database
        await self.db.store_message(user_id, "user", user_text)
        await self.db.store_message(user_id, "assistant", response)
        
        # Extract and store facts from conversation
        await self.memory_service.extract_and_store_facts(user_id, user_text, response)
        
        # Update affection
        affection_change = RelationshipManager.calculate_affection_change(user_text)
        await RelationshipManager.update_affection(self.db, user_id, affection_change)
        
        # Update message count
        await self.db.increment_message_count(user_id)
