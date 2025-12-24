"""Message handler for Luna Bot."""
import json
import logging
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from settings import PARIS_TZ, PAYMENT_LINK
from middleware.metrics import metrics
from middleware.rate_limit import rate_limiter
from middleware.sanitize import sanitize_input, detect_engagement_signal

from services.db import (
    get_pool, save_message, get_history,
    get_or_create_user, get_user_memory, update_user_memory, increment_message_count,
    update_last_active, get_user_data, update_teasing_stage,
    get_emotional_state, set_emotional_state, set_last_message_time,
    get_inside_jokes, update_inside_jokes, get_pending_events, update_pending_events,
    update_attachment_score, increment_session_count, increment_vulnerabilities,
    get_psychology_data, get_last_message_time,
    get_mood_state, update_luna_mood,
    get_momentum_state, update_momentum_state, start_climax_recovery,
    get_trust_state, update_trust_score, add_unlocked_secret,
    get_user_intent, set_user_intent, get_aha_triggered, set_aha_triggered,
)
from services.psychology.variable_rewards import VariableRewardsEngine, RewardContext
from services.psychology.inside_jokes import InsideJokesEngine, InsideJoke
from services.psychology.intermittent import IntermittentEngine
from services.psychology.memory_callbacks import MemoryCallbacksEngine, PendingEvent
from services.psychology.attachment import AttachmentTracker
from services.memory import extract_memory, format_memory_for_prompt
from services.mood import get_current_mood, get_mood_instructions
from services.immersion import (
    build_immersion_context, format_immersion_instructions,
    LunaEmotion, get_emotion_for_session
)
from services.availability import send_with_natural_delay
from services.relationship import get_relationship_phase, get_phase_instructions, get_phase_info
from services.trust_system import (
    detect_trust_action, apply_trust_action, get_trust_modifier, get_trust_state as compute_trust_state
)
from services.subscription import (
    is_trial_expired, get_paywall_message, get_post_paywall_response,
    mark_paywall_sent, has_paywall_been_sent,
)
from services.teasing import check_teasing_opportunity
from services.momentum import momentum_engine, Intensity
from services.llm_router import get_llm_config_v3, is_premium_session
from services.prompt_selector import get_prompt_for_tier, get_prompt_for_tier_v7
from services.luna_mood import luna_mood_engine, LunaMood, MoodContext
from services.secrets import secrets_engine
from services.anti_repetition import add_response, check_repetition, get_variety_instruction, should_add_variety_reminder
from services.context_enricher import get_enriched_context
from services.character_anchor import get_anchor_instruction, get_consistency_check
from prompts.deflect import get_deflect_prompt, get_luna_initiates_prompt
from services.llm import call_with_graceful_fallback
from services import conversion
from services.aha_moment import should_trigger_aha, get_aha_instruction
from services.intent_detection import (
    detect_intent_from_messages, should_detect_intent,
    get_intent_modifier, UserIntent
)


logger = logging.getLogger(__name__)

# Extraction memoire tous les X messages
MEMORY_EXTRACTION_INTERVAL = 5

# V5: Psychology engines (singletons)
variable_rewards = VariableRewardsEngine()
inside_jokes = InsideJokesEngine()
intermittent = IntermittentEngine()
memory_callbacks = MemoryCallbacksEngine()
attachment_tracker = AttachmentTracker()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal avec tous les systemes integres + V5 psychology."""
    tg_user = update.effective_user
    telegram_id = tg_user.id

    # CRITICAL FIX: Sanitization des entrees
    user_text = sanitize_input(update.message.text)
    if not user_text:
        return

    # HIGH FIX: Rate limiting robuste (sliding window)
    if not rate_limiter.is_allowed(telegram_id):
        wait_time = rate_limiter.get_wait_time(telegram_id)
        logger.warning(f"Rate limit: {tg_user.first_name} (wait {wait_time:.0f}s)")
        return

    logger.info(f"[{tg_user.first_name}] {user_text[:100]}...")

    # Track metrics
    metrics.record_message()

    # 1. Get/create user
    user = await get_or_create_user(telegram_id)
    user_id = user["id"]

    # 2. Update last_active + last_message_at (persistant)
    last_msg_time = await get_last_message_time(user_id)
    hours_since_last = 0
    if last_msg_time:
        hours_since_last = (datetime.now(last_msg_time.tzinfo or None) - last_msg_time).total_seconds() / 3600

    await update_last_active(user_id)
    await set_last_message_time(user_id)

    # V5: Track sessions (nouvelle session si >4h d'inactivite)
    is_new_session = hours_since_last > 4
    if is_new_session:
        await increment_session_count(user_id)

    # 3. Sauvegarder message user
    await save_message(user_id, "user", user_text)

    # 4. Incrementer compteur
    msg_count = await increment_message_count(user_id)

    # 5. Recuperer donnees utilisateur completes
    user_data = await get_user_data(user_id)
    first_message_at = user_data.get("first_message_at")

    # 6. Calculer phase par msg_count (V7)
    phase, _ = get_relationship_phase(msg_count)
    phase_info = get_phase_info(msg_count)

    # 6b. Calculer day_count pour compatibilité (momentum, teasing)
    if first_message_at:
        if first_message_at.tzinfo is None:
            first_message_at = first_message_at.replace(tzinfo=PARIS_TZ)
        day_count = (datetime.now(PARIS_TZ) - first_message_at).days + 1
    else:
        day_count = 1

    # 6c. Recuperer trust state (V7)
    trust_data = await get_trust_state(user_id)
    trust_score = trust_data.get("trust_score", 50)
    luna_last_state = trust_data.get("luna_last_state", "neutral")

    # 7. Verifier subscription (paywall apres 5 jours, sauf si abonne)
    subscription_status = user_data.get("subscription_status", "trial")
    if subscription_status != "active" and first_message_at and is_trial_expired(first_message_at):
        paywall_sent = await has_paywall_been_sent(user_id, get_pool())

        if not paywall_sent:
            paywall_msg = get_paywall_message(first_message_at, user_id)
            await update.message.reply_text(paywall_msg)
            await save_message(user_id, "assistant", paywall_msg)
            await mark_paywall_sent(user_id, get_pool())
            logger.info(f"Paywall envoye a user {user_id}")
            return
        else:
            response = get_post_paywall_response()
            await update.message.reply_text(response)
            await save_message(user_id, "assistant", response)
            return

    # 8. Recuperer historique + memoire
    history = await get_history(user_id)
    memory = await get_user_memory(user_id)

    # 9. Determiner mood
    mood = get_current_mood()

    # 10. Get emotional state from DB (persistant)
    emotional_state = await get_emotional_state(user_id)

    # V5: Get psychology data
    psych_data = await get_psychology_data(user_id)
    existing_jokes = [InsideJoke.from_dict(j) for j in psych_data.get("inside_jokes", [])]
    pending_events = [PendingEvent.from_dict(e) for e in psych_data.get("pending_events", [])]

    logger.info(f"User {user_id}: Phase={phase}({msg_count}msgs), Trust={trust_score}, Mood={mood}")

    # ============== V3: MOMENTUM SYSTEM ==============
    # Get current momentum state
    momentum_state = await get_momentum_state(user_id)
    current_momentum = momentum_state["momentum"]
    intimacy_history = momentum_state["intimacy_history"]
    messages_since_climax = momentum_state["messages_since_climax"]
    messages_this_session = momentum_state["messages_this_session"]
    last_message_at = momentum_state["last_message_at"]

    # V7: Apply time-based decay BEFORE calculating new momentum
    decayed_momentum = momentum_engine.apply_time_decay(
        current_momentum,
        last_message_at,
        messages_since_climax
    )
    if decayed_momentum != current_momentum:
        current_momentum = decayed_momentum

    # Classify message intensity and calculate new momentum
    new_momentum, intensity, is_negative_emotion = momentum_engine.calculate_momentum(
        user_text,
        current_momentum,
        messages_this_session,
        day_count
    )

    # V7: Apply SFW decay boost for faster return to normal after NSFW session
    sfw_boost = momentum_engine.get_sfw_decay_boost(intensity, messages_since_climax)
    if sfw_boost > 0:
        new_momentum = max(0, new_momentum - sfw_boost)

    # Check for climax in user message (use detect_climax_user, NOT detect_climax)
    user_climax = False
    is_climax_msg = momentum_engine.detect_climax_user(user_text)
    if intensity == Intensity.NSFW and is_climax_msg:
        user_climax = True
        new_momentum = momentum_engine.apply_climax_cooldown(new_momentum)
        logger.info(f"V3: User climax detected, momentum reduced to {new_momentum:.1f}")

    # Determine modifier based on state
    level_modifier = None

    # 1. Check emotional distress first
    if is_negative_emotion:
        level_modifier = "USER_DISTRESSED"
        logger.info("V3: Negative emotion detected, applying USER_DISTRESSED")

    # 2. Check recovery phase (after climax)
    elif user_climax:
        level_modifier = "AFTERCARE"
        messages_since_climax = 0  # Will be set after response
    elif messages_since_climax <= 3:
        level_modifier = momentum_engine.get_recovery_modifier(messages_since_climax)
        if level_modifier:
            logger.info(f"V3: Recovery phase, applying {level_modifier}")

    # 3. Apply soft caps based on phase (only for HOT/NSFW escalation attempts)
    elif not level_modifier and intensity in (Intensity.HOT, Intensity.NSFW):
        soft_cap = momentum_engine.apply_soft_cap(intensity, day_count, messages_this_session, new_momentum)
        if soft_cap.modifier:
            level_modifier = soft_cap.modifier
            logger.info(f"V3: Soft cap applied: {soft_cap.modifier}")

    # Get tier based on momentum
    tier = momentum_engine.get_tier(new_momentum, day_count, intimacy_history)

    logger.info(f"V3 Momentum: {current_momentum:.1f} -> {new_momentum:.1f}, intensity={intensity.value}, tier={tier}")

    # ============== V8: LUNA MOOD SYSTEM ==============
    current_hour = datetime.now(PARIS_TZ).hour

    # Get mood state from DB
    mood_state = await get_mood_state(user_id)
    current_luna_mood = LunaMood(mood_state["luna_mood"])
    mood_updated_at = mood_state["mood_updated_at"]
    last_horny_at = mood_state["last_horny_at"]
    last_climax_at = mood_state["last_climax_at"]

    # Calculate hours since climax
    hours_since_climax = 999.0
    if last_climax_at:
        if last_climax_at.tzinfo is None:
            last_climax_at = last_climax_at.replace(tzinfo=timezone.utc)
        hours_since_climax = (datetime.now(last_climax_at.tzinfo) - last_climax_at).total_seconds() / 3600

    # Check if mood should be updated (every 2-4 hours)
    if luna_mood_engine.should_update_mood(mood_updated_at):
        # Build mood context for V7 8-state system
        mood_ctx = MoodContext(
            current_hour=current_hour,
            day_of_week=datetime.now(PARIS_TZ).weekday(),
            hours_since_last_message=hours_since_last,
            user_sentiment=None,  # TODO: detect from message
            last_luna_state=luna_last_state,
            trust_score=trust_score,
            phase=phase
        )
        new_luna_mood = luna_mood_engine.calculate_new_mood(mood_ctx, current_luna_mood)
        if new_luna_mood != current_luna_mood:
            await update_luna_mood(user_id, new_luna_mood.value)
            current_luna_mood = new_luna_mood
            logger.info(f"V8: Luna mood updated to {new_luna_mood.value}")

    # Check for immediate mood trigger from user message
    triggered_mood = luna_mood_engine.detect_mood_trigger(user_text, current_luna_mood)
    if triggered_mood and triggered_mood != current_luna_mood:
        await update_luna_mood(user_id, triggered_mood.value)
        current_luna_mood = triggered_mood
        logger.info(f"V8: Mood triggered by message -> {triggered_mood.value}")

    # Check availability for NSFW escalation (HOT or NSFW intensity)
    minutes_since_climax = hours_since_climax * 60
    is_escalating = intensity in (Intensity.HOT, Intensity.NSFW)
    availability_result = luna_mood_engine.check_availability(
        mood=current_luna_mood,
        minutes_since_climax=minutes_since_climax,
        current_hour=current_hour,
        momentum=new_momentum,
        intensity_is_nsfw=is_escalating
    )

    # Handle Luna initiates (JACKPOT!)
    luna_initiates = availability_result.luna_initiates
    should_deflect = availability_result.should_deflect
    deflect_type = availability_result.deflect_type

    if luna_initiates:
        logger.info(f"V8: JACKPOT! Luna initiates NSFW (mood={current_luna_mood.value})")
        level_modifier = "LUNA_INITIATES"
    elif should_deflect and tier >= 2:
        logger.info(f"V8: Deflecting NSFW attempt (type={deflect_type}, availability={availability_result.score:.2f})")
        level_modifier = f"DEFLECT_{deflect_type.upper()}" if deflect_type else "DEFLECT_PLAYFUL"
        # Force tier down when deflecting
        tier = min(tier, 2)

    # 11. Progress emotional state if user responded
    if emotional_state == "opener":
        await set_emotional_state(user_id, "follow_up")
        emotional_state = "follow_up"
    elif emotional_state == "follow_up":
        await set_emotional_state(user_id, "resolution")
        emotional_state = "resolution"
    elif emotional_state == "resolution":
        await set_emotional_state(user_id, None)
        emotional_state = None

    # V5: Intermittent reinforcement - get current state
    intermittent_state = intermittent.get_state(user_id, day_count, hours_since_last)
    affection_instruction = intermittent.get_affection_instruction(intermittent_state)

    # V5: Check for inside joke opportunities
    joke_opportunity = None
    if inside_jokes.should_create(day_count, len(existing_jokes)):
        joke_opportunity = inside_jokes.detect_opportunity(user_text, existing_jokes)
        if joke_opportunity:
            new_joke = inside_jokes.create_joke(joke_opportunity)
            existing_jokes.append(new_joke)
            await update_inside_jokes(user_id, [j.to_dict() for j in existing_jokes])
            logger.info(f"Created inside joke: {new_joke.value}")

    # V5: Extract pending events from user message
    new_events = memory_callbacks.extract_pending_events(user_text)
    if new_events:
        pending_events.extend(new_events)
        await update_pending_events(user_id, [e.to_dict() for e in pending_events])

    # V5: Check for vulnerability indicators
    vulnerability_words = ["j'ai peur", "je me sens seul", "j'avoue", "entre nous", "j'ai jamais dit"]
    if any(vw in user_text.lower() for vw in vulnerability_words):
        await increment_vulnerabilities(user_id)

    # 12. Check teasing opportunity (J2-5)
    teasing_msg = None
    if 2 <= day_count <= 5:
        teasing_msg = check_teasing_opportunity(day_count, user_data)
        if teasing_msg:
            await update_teasing_stage(user_id, user_data.get("teasing_stage", 0) + 1)

    # V5: Build extra instructions for LLM
    extra_instructions = []
    if affection_instruction:
        extra_instructions.append(affection_instruction)

    # ============== PHASE A: Intent Detection ==============
    current_intent = await get_user_intent(user_id)
    if should_detect_intent(msg_count, current_intent):
        # Récupérer les premiers messages pour détecter l'intent
        first_messages = [m["content"] for m in history[-5:] if m["role"] == "user"]
        first_messages.append(user_text)
        detected_intent = detect_intent_from_messages(first_messages)
        await set_user_intent(user_id, detected_intent.value)
        current_intent = detected_intent.value
        logger.info(f"Phase A: Intent detected = {detected_intent.value}")

    # Ajouter le modifier d'intent si détecté
    if current_intent:
        intent_enum = UserIntent(current_intent)
        intent_mod = get_intent_modifier(intent_enum)
        if intent_mod:
            extra_instructions.append(intent_mod)

    # ============== PHASE A: AHA Moment ==============
    aha_triggered = await get_aha_triggered(user_id)
    if should_trigger_aha(msg_count, aha_triggered):
        aha_instruction = get_aha_instruction(memory or {}, user_text)
        extra_instructions.append(aha_instruction)
        await set_aha_triggered(user_id)
        logger.info(f"Phase A: AHA moment triggered at msg {msg_count}")

    # V5: Memory callback instruction
    memory_instruction = memory_callbacks.get_memory_instruction(memory)
    if memory_instruction:
        extra_instructions.append(memory_instruction)

    # V7: Trust modifier
    trust_modifier = get_trust_modifier(trust_score)
    if trust_modifier:
        extra_instructions.append(trust_modifier)
        logger.info(f"V7 Trust: modifier applied (score={trust_score})")

    # V8: Mood prompt (8 états émotionnels)
    mood_prompt = luna_mood_engine.get_mood_prompt(current_luna_mood)
    if mood_prompt:
        extra_instructions.append(mood_prompt)
        logger.info(f"V8 Mood: {current_luna_mood.value} prompt applied")

    # V9: Immersion context (temporalité, vie Luna, émotions, jalousie)
    immersion_ctx = build_immersion_context(
        last_message_at=last_msg_time,
        current_hour=current_hour,
        day_count=day_count,
        messages_this_session=messages_this_session,
        user_message=user_text,
    )
    immersion_instructions = format_immersion_instructions(immersion_ctx)
    if immersion_instructions:
        extra_instructions.append(immersion_instructions)
        logger.info(f"V9 Immersion: added context instructions")

    # V5: Inside joke callback
    if existing_jokes and not joke_opportunity:
        for joke in existing_jokes:
            callback = inside_jokes.get_callback(joke, day_count)
            if callback:
                extra_instructions.append(f"\n## INSIDE JOKE\nMentionne naturellement: {callback}")
                joke.times_referenced += 1
                joke.last_referenced = datetime.now()
                await update_inside_jokes(user_id, [j.to_dict() for j in existing_jokes])
                break

    # V7: Secrets revelation (layers system)
    unlocked_secrets = trust_data.get("unlocked_secrets", [])
    secret_to_reveal = secrets_engine.should_reveal_secret(
        phase=phase,
        trust_score=trust_score,
        unlocked_secrets=unlocked_secrets,
        context=user_text
    )
    if secret_to_reveal:
        secret_instruction = secrets_engine.get_secret_instruction(secret_to_reveal)
        extra_instructions.append(secret_instruction)
        # Mark secret as unlocked
        await add_unlocked_secret(user_id, secret_to_reveal.id)
        logger.info(f"V7 Secret: revealing '{secret_to_reveal.id}' (layer {secret_to_reveal.layer})")

    # ============== FIX 1: Anti-répétition ==============
    if should_add_variety_reminder(user_id):
        extra_instructions.append(get_variety_instruction())
        logger.info("Anti-rep: variety reminder added")

    # ============== FIX 2: Context enrichi ==============
    enriched_ctx = get_enriched_context(
        hour=current_hour,
        day_of_week=datetime.now(PARIS_TZ).weekday(),
        msg_count=msg_count,
        include_pixel=True,
        include_activity=True,
        include_struggle=(msg_count > 30)
    )
    if enriched_ctx:
        extra_instructions.append(enriched_ctx)
        logger.info("Context enrichi added")

    # ============== FIX 3: Character anchor ==============
    anchor = get_anchor_instruction(msg_count)
    if anchor:
        extra_instructions.append(anchor)
        logger.info(f"Character anchor injected at msg {msg_count}")

    consistency = get_consistency_check(phase, msg_count)
    if consistency:
        extra_instructions.append(consistency)

    # ============== V3: LLM Router (Tier-based) ==============
    teasing_stage = user_data.get("teasing_stage", 0)
    subscription_status = user_data.get("subscription_status", "trial")

    # V3: Get provider and model based on momentum and tier
    provider, model, final_tier = get_llm_config_v3(
        momentum=new_momentum,
        day_count=day_count,
        intimacy_history=intimacy_history,
        subscription_status=subscription_status,
        detected_intensity=intensity,
        modifier=level_modifier
    )

    logger.info(f"V3 Router: provider={provider}, tier={final_tier}, modifier={level_modifier}")

    # V6: Track premium preview + check if conversion needed AFTER response
    show_conversion_after = False
    if is_premium_session(provider) and subscription_status != "active":
        preview_count = await conversion.increment_preview_count(user_id)
        logger.info(f"Premium preview count: {preview_count}")

        # Check if we should show conversion flow (but after responding)
        if await conversion.should_show_conversion(
            user_id, day_count, teasing_stage, subscription_status
        ):
            show_conversion_after = True

    # V7: Build system prompt based on tier with NSFW state support
    # Get user context for NSFW prompts
    user_name = (memory.get("prenom") if memory else None) or "lui"
    inside_jokes_list = [j.value for j in existing_jokes] if existing_jokes else []
    pet_names_list = (memory.get("pet_names") if memory else None) or []

    # Get NSFW state for tier 3
    nsfw_state = momentum_engine.get_nsfw_state(new_momentum, messages_since_climax)

    # V8: Handle deflect prompts and luna initiates
    if luna_initiates:
        system_prompt = get_luna_initiates_prompt()
        logger.info(f"V8: Using LUNA_INITIATES prompt (JACKPOT!)")
    elif should_deflect and deflect_type:
        system_prompt = get_deflect_prompt(deflect_type)
        logger.info(f"V8: Using DEFLECT prompt: {deflect_type}")
    # Use V7 prompt selector for tier 3, otherwise use regular
    elif final_tier >= 3:
        system_prompt = get_prompt_for_tier_v7(
            tier=final_tier,
            nsfw_state=nsfw_state,
            user_name=user_name,
            inside_jokes=inside_jokes_list,
            pet_names=pet_names_list,
            modifier=level_modifier
        )
        logger.info(f"V7 NSFW: state={nsfw_state}, user={user_name}")
    else:
        system_prompt = get_prompt_for_tier(final_tier, level_modifier)

    # 13. Generer reponse avec graceful fallback
    try:
        # Build messages for LLM
        messages = history.copy()
        messages.append({"role": "user", "content": user_text})

        # Add context to prompt
        prompt_parts = [system_prompt]
        if memory:
            prompt_parts.append(f"\n## CE QUE TU SAIS SUR LUI:\n{format_memory_for_prompt(memory)}")
        prompt_parts.append(get_phase_instructions(phase, msg_count))
        prompt_parts.append(f"\n## TON HUMEUR:\n{get_mood_instructions(mood)}")
        if extra_instructions:
            prompt_parts.append(f"\n## INSTRUCTIONS:\n" + "\n".join(extra_instructions))

        full_prompt = "\n".join(prompt_parts)

        # Call with graceful fallback
        response = await call_with_graceful_fallback(
            messages=messages,
            system_prompt=full_prompt,
            provider=provider,
            model=model,
            tier=final_tier
        )
        metrics.record_llm_call(success=True)
    except Exception as e:
        metrics.record_llm_call(success=False)
        metrics.record_error(str(e))
        logger.error(f"LLM generation failed: {e}")
        response = random.choice([
            "attends j'ai pas capte",
            "hein ? j'etais ailleurs desolee",
            "pardon j'ai decroche 2 sec",
            "oups j'ai pas suivi",
        ])

    # V5: Modify response based on intermittent affection
    response = intermittent.modify_response(response, intermittent_state)

    # ⛔ CRITICAL: Filter out AI admissions
    ai_admission_patterns = [
        "je suis une ia", "chui une ia", "suis une ia",
        "je suis un bot", "chui un bot", "suis un bot",
        "je suis une intelligence artificielle",
        "on est deux ia", "nous sommes des ia",
        "je suis un programme", "je suis artificielle",
        "je suis pas réelle", "je suis pas humaine",
        "je suis virtuelle", "je suis pas une vraie"
    ]
    response_lower = response.lower()
    if any(pattern in response_lower for pattern in ai_admission_patterns):
        logger.warning(f"⛔ AI ADMISSION BLOCKED: {response}")
        response = "mdrr quoi?? 😂 nn chui luna, une meuf normale de paris. pk tu demandes ça?"

    # V5: Check variable rewards (skip during critical moments)
    # Skip during: NSFW tier 3, aftercare/recovery, negative emotions
    skip_rewards_modifiers = {"AFTERCARE", "POST_INTIMATE", "POST_NSFW", "USER_DISTRESSED"}
    should_skip_rewards = tier >= 3 or level_modifier in skip_rewards_modifiers
    if not should_skip_rewards:
        reward_context = RewardContext(
            user_id=user_id,
            phase=day_count,
            day_count=day_count,
            messages_this_session=msg_count % 50,  # Approximation
            user_message=user_text,
            memory=memory,
            conversation_sentiment="positive" if any(e in user_text.lower() for e in ["merci", "cool", "super", "j'aime"]) else "neutral"
        )
        reward = variable_rewards.check_reward(reward_context)
        if reward:
            reward_type, reward_msg = reward
            response = response + "\n\n" + reward_msg
            logger.info(f"Variable reward added: {reward_type.value}")

    # V5: Add inside joke creation message if opportunity
    if joke_opportunity:
        response = response + "\n\n" + joke_opportunity.creation_message

    # 14. Ajouter teasing si opportun
    if teasing_msg:
        response = response + "\n\n" + teasing_msg

    # 15. Sauvegarder reponse Luna
    await save_message(user_id, "assistant", response)

    # FIX 1: Cache response for anti-repetition
    add_response(user_id, response)

    logger.info(f"[Luna] {response}")

    # V3: Check for climax in Luna's response
    luna_climax = False
    if not user_climax and final_tier >= 3 and momentum_engine.detect_climax(response):
        luna_climax = True
        new_momentum = momentum_engine.apply_climax_cooldown(new_momentum)
        logger.info(f"V3: Luna climax detected, momentum reduced to {new_momentum:.1f}")

    # V3: Update momentum state
    if user_climax or luna_climax:
        # Start climax recovery (increments intimacy_history)
        await start_climax_recovery(user_id, new_momentum)
        logger.info(f"V3: Climax recovery started, intimacy_history incremented")
    else:
        # Normal momentum update
        await update_momentum_state(
            user_id=user_id,
            momentum=new_momentum,
            tier=final_tier,
            messages_this_session=messages_this_session + 1
        )

    # 16. Extraction memoire periodique
    if msg_count % MEMORY_EXTRACTION_INTERVAL == 0:
        try:
            logger.info(f"Extraction memoire pour user {user_id} (msg #{msg_count})")
            updated_history = await get_history(user_id, limit=10)
            new_memory = await extract_memory(updated_history, memory)
            await update_user_memory(user_id, new_memory)
        except Exception as e:
            logger.error(f"Memory extraction failed for user {user_id}: {e}")

    # V5: Update attachment score periodically
    if msg_count % 10 == 0:
        try:
            # Recuperer les messages pour analyse
            all_history = await get_history(user_id, limit=50)
            user_messages_content = [m["content"] for m in all_history if m["role"] == "user"]

            score_data = {
                "user_messages": len([m for m in all_history if m["role"] == "user"]),
                "luna_messages": len([m for m in all_history if m["role"] == "assistant"]),
                "session_count": psych_data.get("session_count", 1),
                "user_initiated_count": psych_data.get("user_initiated_count", 0),
                "inside_jokes_count": len(existing_jokes),
                "vulnerabilities_shared": psych_data.get("vulnerabilities_shared", 0),
                "total_messages": msg_count,
                "user_messages_content": user_messages_content,
                "response_times": [],  # TODO: track response times
            }
            attachment_metrics = attachment_tracker.calculate_score(score_data)
            await update_attachment_score(user_id, attachment_metrics.score)
            logger.info(f"Attachment score updated: {attachment_metrics.score:.1f}")
        except Exception as e:
            logger.error(f"Attachment score update failed: {e}")

    # V6: Update teasing stage based on engagement signals
    engagement_increment = detect_engagement_signal(user_text)
    if engagement_increment > 0:
        new_teasing_stage = min(teasing_stage + engagement_increment, 8)
        if new_teasing_stage > teasing_stage:
            await update_teasing_stage(user_id, new_teasing_stage)
            logger.info(f"Teasing stage updated: {teasing_stage} -> {new_teasing_stage}")

    # V7: Detect and apply trust actions
    trust_action = detect_trust_action(
        user_message=user_text,
        luna_last_state=luna_last_state,
        memory=memory,
        hours_since_last=hours_since_last
    )
    if trust_action:
        new_trust = apply_trust_action(trust_score, trust_action)
        # Determine Luna's current state based on mood/context
        current_luna_state = mood if mood in ("vulnerable", "anxious", "stressed") else "neutral"
        await update_trust_score(user_id, new_trust, current_luna_state)
        logger.info(f"V7 Trust: {trust_action.action_id} applied, score={trust_score}→{new_trust}")

    # 17. Envoyer avec delai naturel (+ intermittent delay modifier)
    delay_modifier = intermittent.get_delay_modifier(intermittent_state)
    await send_with_natural_delay(update, response, mood, delay_modifier)

    # V6: Show conversion flow AFTER response (not instead of)
    if show_conversion_after:
        await send_conversion_flow(update, context, user_id)


async def send_conversion_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Envoie le flow de conversion naturel vers l'abonnement."""
    import asyncio

    telegram_id = update.effective_user.id

    # Envoyer les messages de transition
    messages = conversion.get_transition_messages()

    for msg in messages:
        await asyncio.sleep(random.uniform(2, 4))
        await context.bot.send_chat_action(chat_id=telegram_id, action="typing")
        await asyncio.sleep(random.uniform(1, 2))
        await context.bot.send_message(chat_id=telegram_id, text=msg)
        await save_message(user_id, "assistant", msg)

    await asyncio.sleep(2)

    # Envoyer le CTA d'abonnement
    cta = conversion.get_cta()

    if PAYMENT_LINK:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(cta["button"], url=PAYMENT_LINK)]
        ])
        await context.bot.send_message(
            chat_id=telegram_id,
            text=cta["text"],
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(chat_id=telegram_id, text=cta["text"])

    # Marquer conversion montree
    await conversion.mark_conversion_shown(user_id)
    logger.info(f"Conversion flow sent to user {user_id}")
