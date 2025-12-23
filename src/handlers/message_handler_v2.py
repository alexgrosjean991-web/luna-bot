"""
Message Handler V2
Architecture refactorée avec state machine et inner world.
"""

import logging
import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction

from src.services.llm_service import llm_service
from src.services.memory_service import MemoryService, ConversionManager, RelationshipManager
from src.services.prompt_assembler import prompt_assembler
from src.services.conversation_state import ConversationState
from src.services.inner_world import inner_world
from src.services.humanizer_fr import humanizer_fr
from src.services.humanizer_en import humanizer_en
from src.services.realistic_delays import delay_service, typing_simulator, split_message_naturally

logger = logging.getLogger(__name__)


class MessageHandlerV2:
    """
    Message handler refactoré.
    Plus simple, plus modulaire, plus maintenable.
    """

    def __init__(self, db):
        self.db = db
        self.memory_service = MemoryService(db)

    async def handle_message(self, update: Update, context) -> None:
        """Main message handler"""
        user = update.effective_user
        message = update.message
        user_text = message.text

        if not user_text:
            return

        # === GET USER DATA ===
        db_user = await self.db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code or "en"
        )

        user_id = db_user['id']
        is_french = db_user.get('language_code', 'en').startswith('fr')
        user_name = db_user.get('first_name') or user.first_name

        # === GET LUNA STATE ===
        luna_state = await self.db.get_luna_state(user_id)
        affection = luna_state.get('affection_level', 10)
        is_converted = await ConversionManager.is_converted(self.db, user_id)

        # === HANDLE SPECIAL INPUTS (?, emoji, ok, lol) ===
        special_response = self._handle_special_input(user_text, is_french, affection)
        if special_response:
            await self._send_quick_response(message, context, special_response, user_id, user_text)
            return

        # === CHECK TRIAL LIMITS ===
        should_limit, _ = await ConversionManager.should_limit_messages(self.db, user_id)
        if should_limit and not is_converted:
            await self._handle_trial_limit(message, is_french)
            return

        # === SHOW TYPING ===
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        # === GET CONTEXT DATA ===
        history = await self.db.get_conversation_history(user_id, limit=15)
        memories = await self.memory_service.get_memories(user_id)
        last_luna_msg = history[-1]['content'] if history and history[-1]['role'] == 'assistant' else ""

        # === ASSEMBLE PROMPT ===
        system_prompt = prompt_assembler.assemble(
            user_id=user_id,
            user_name=user_name,
            affection=affection,
            is_converted=is_converted,
            user_message=user_text,
            memories=memories,
            last_luna_message=last_luna_msg,
            lang="fr" if is_french else "en"
        )

        # === ADD SPECIAL CONTEXTS ===
        system_prompt = await self._add_special_contexts(
            system_prompt, user_id, user_text, history, affection, is_french
        )

        # === DETERMINE MODEL ===
        use_nsfw_model = prompt_assembler.should_use_nsfw_model(user_id)
        current_state = prompt_assembler.get_current_state(user_id)

        logger.info(f"State: {current_state.value if current_state else 'none'}, NSFW model: {use_nsfw_model}")

        # === GENERATE RESPONSE ===
        api_messages = [{"role": msg['role'], "content": msg['content']} for msg in history]
        api_messages.append({"role": "user", "content": user_text})

        response = await llm_service.generate_response(
            system_prompt=system_prompt,
            messages=api_messages,
            is_nsfw=use_nsfw_model,
            is_french=is_french
        )

        # === SEND WITH REALISTIC DELAYS ===
        await self._send_with_delays(
            message, context, response, user_id, user_text,
            affection, is_french, use_nsfw_model, is_converted
        )

        # === UPDATE DATABASE ===
        await self.db.store_message(user_id, "user", user_text)
        await self.db.store_message(user_id, "assistant", response)
        await self.memory_service.extract_and_store_facts(user_id, user_text, response)

        affection_change = RelationshipManager.calculate_affection_change(user_text)
        await RelationshipManager.update_affection(self.db, user_id, affection_change)
        await self.db.increment_message_count(user_id)

    def _handle_special_input(self, text: str, is_french: bool, affection: float) -> Optional[str]:
        """Gère les inputs spéciaux (?, emoji, ok, lol)"""
        import re
        text_stripped = text.strip().lower()

        # Message = juste "?"
        if text_stripped in ["?", "??"]:
            return random.choice(["quoi? 👀", "hm?", "??", "quoi"] if is_french else ["what? 👀", "hm?", "??"])

        # Message = "..."
        if text_stripped in ["...", "..", "…"]:
            return random.choice(["quoi?", "bah dis", "..."] if is_french else ["what?", "say it", "..."])

        # Emoji seul
        emoji_pattern = re.compile(r"[\U0001F600-\U0001F9FF]+", re.UNICODE)
        if emoji_pattern.fullmatch(text.strip()):
            if any(e in text for e in ["❤️", "💕", "🥰", "😍"]):
                return random.choice(["❤️", "🥰", "aww"] if affection > 50 else ["☺️", "hehe"])
            elif any(e in text for e in ["😏", "😈", "🔥"]):
                return random.choice(["😏", "oh?", "hm 👀"] if affection > 40 else ["mdr", "👀"])
            return random.choice([text.strip(), "😊", "mdr"])

        # Messages ultra courts
        dismissive = {
            "ok": ["okay?", "juste ok?", "..."],
            "lol": ["mdr", "😂", "c'était drôle?"],
            "mdr": ["😂", "t'es bête", "mdrr"],
            "hmm": ["quoi?", "tu penses à quoi", "hm?"],
            "oui": ["oui quoi?", "oui?", "okay"],
            "non": ["non quoi?", "pourquoi non", "??"],
        }
        if text_stripped in dismissive:
            return random.choice(dismissive[text_stripped])

        return None

    async def _send_quick_response(self, message, context, response: str, user_id: int, user_text: str):
        """Envoie une réponse rapide pour les inputs spéciaux"""
        await asyncio.sleep(random.uniform(0.5, 2.0))
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.3, 1.0))
        await message.reply_text(response)
        await self.db.store_message(user_id, "user", user_text)
        await self.db.store_message(user_id, "assistant", response)
        await self.db.increment_message_count(user_id)

    async def _handle_trial_limit(self, message, is_french: bool):
        """Gère la limite d'essai"""
        if random.random() < 0.7:
            busy_msgs = [
                "désolée jsuis trop busy au taf",
                "j'aimerais trop te parler plus",
                "tu me manques"
            ] if is_french else [
                "sorry been super busy at work",
                "i wish i could talk more",
                "miss you"
            ]
            await asyncio.sleep(random.uniform(30, 90))
            await message.reply_text(random.choice(busy_msgs))

    async def _add_special_contexts(
        self, prompt: str, user_id: int, user_text: str,
        history: list, affection: float, is_french: bool
    ) -> str:
        """Ajoute les contextes spéciaux au prompt"""

        # Anti-répétition
        if len(history) >= 5:
            luna_responses = [m['content'] for m in history if m['role'] == 'assistant'][-5:]
            if luna_responses:
                from collections import Counter
                openings = [r.split()[0].lower() if r else "" for r in luna_responses]
                opening_counts = Counter(openings)
                repeated = [o for o, c in opening_counts.items() if c >= 2 and o]
                if repeated:
                    prompt += f"\n\nÉVITE de commencer par: {', '.join(repeated)}"

        # Détection test IA
        ai_tests = ["t'es une ia", "tu es un bot", "are you ai", "chatgpt", "gpt"]
        if any(t in user_text.lower() for t in ai_tests):
            prompt += """

ALERTE: IL TE TESTE. Réponds: "mdr quoi", "euh rude??", "t'es chelou" puis change de sujet."""

        # Mémoire callback (15% chance)
        if random.random() < 0.15 and affection > 30:
            callback = await self.memory_service.get_callback_memory(user_id)
            if callback:
                prompt += f"\n\nSOUVENIR: Tu peux mentionner naturellement: {callback}"

        return prompt

    async def _send_with_delays(
        self, message, context, response: str, user_id: int, user_text: str,
        affection: float, is_french: bool, is_nsfw: bool, is_converted: bool
    ):
        """Envoie le message avec des délais réalistes"""
        hour = datetime.now().hour

        # Déterminer le mood
        if affection > 70:
            mood = "flirty"
        elif affection > 40:
            mood = "playful"
        elif hour >= 23 or hour < 7:
            mood = "tired"
        else:
            mood = "happy"

        # Calculer le délai
        delay_result = delay_service.calculate_delay(
            user_id=user_id,
            user_message=user_text,
            response=response,
            affection=affection,
            hour=hour,
            mood=mood,
            is_converted=is_converted,
            is_french=is_french,
            is_nsfw=is_nsfw
        )

        # Délai initial
        if delay_result.initial_delay > 0:
            await asyncio.sleep(delay_result.initial_delay)

        # Simulation typing
        await typing_simulator.simulate_typing(context, message.chat_id, delay_result)

        # Excuse si lent
        if delay_result.add_excuse and delay_result.excuse_text:
            await message.reply_text(delay_result.excuse_text)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(random.uniform(1.0, 2.0))

        # Split et envoyer
        messages = split_message_naturally(response, delay_result.split_count)
        humanizer = humanizer_fr if is_french else humanizer_en

        for i, msg in enumerate(messages):
            if i > 0:
                pause = random.uniform(0.8, 2.5) if mood == "flirty" else random.uniform(1.5, 4.0)
                await asyncio.sleep(pause)
                await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(random.uniform(0.5, 1.5))

            humanized = await humanizer.humanize_text(msg, mood)
            await message.reply_text(humanized)
