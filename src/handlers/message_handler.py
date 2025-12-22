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
from src.prompts.luna_persona_en import build_system_prompt
from src.prompts.luna_persona_fr import build_system_prompt_fr

logger = logging.getLogger(__name__)

class MessageHandler:
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
        
        # Get user day and conversion status
        day_number = await ConversionManager.get_user_day(self.db, user_id)
        is_converted = await ConversionManager.is_converted(self.db, user_id)
        
        # Check if should limit messages (post-trial, not converted)
        should_limit, limit_reason = await ConversionManager.should_limit_messages(self.db, user_id)
        
        if should_limit and not is_converted:
            # Luna is "busy" - respond sparsely
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
        
        # Get Luna state
        luna_state = await self.db.get_luna_state(user_id)
        
        # Build system prompt
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
        
        # Check if should trigger conversion pitch
        messages_today = await self.db.get_messages_today(user_id)
        should_convert = await ConversionManager.should_trigger_conversion(
            self.db, user_id, messages_today
        )
        
        if should_convert:
            # Add conversion context to system prompt
            system_prompt += "\n\nIMPORTANT: This is the moment to naturally bring up your struggles and ask for his help. Be genuine and emotional."
        
        # Format messages for API
        api_messages = [{"role": msg['role'], "content": msg['content']} for msg in history]
        api_messages.append({"role": "user", "content": user_text})
        
        # Check for NSFW
        is_nsfw = llm_service.detect_nsfw(user_text)
        
        # Only allow NSFW if converted and relationship level high enough
        if is_nsfw and (not is_converted or luna_state.get('affection_level', 0) < 75):
            is_nsfw = False  # Fall back to SFW model
        
        # Generate response
        response = await llm_service.generate_response(
            system_prompt=system_prompt,
            messages=api_messages,
            is_nsfw=is_nsfw
        )
        
        # Determine mood for humanizer
        hour = datetime.now().hour
        affection = luna_state.get('affection_level', 10)
        
        if affection > 70:
            mood = "flirty"
        elif affection > 40:
            mood = "playful"
        elif hour >= 23 or hour < 7:
            mood = "tired"
        else:
            mood = "happy"
        
        # Humanize response
        messages_to_send, delay = await humanizer.humanize_response(
            response, mood, len(user_text)
        )
        
        # Wait for typing delay
        await asyncio.sleep(delay)
        
        # Send message(s)
        for i, msg in enumerate(messages_to_send):
            if i > 0:
                await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(random.uniform(1.5, 3.0))
            
            await message.reply_text(msg)
        
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
