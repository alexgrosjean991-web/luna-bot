#!/usr/bin/env python3
"""
Test complet du flow Luna:
1. HOOK phase (nouveau user)
2. Accumulation mémoire (10 messages)
3. Phase LIBRE + NSFW
4. Mémoire injectée en NSFW
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory import (
    set_pool as set_memory_pool,
    set_extraction_api_key,
    init_memory_tables,
    get_or_create_user,
    get_relationship,
    update_relationship,
    extract_unified,
    build_prompt_context,
)
from services.phases import Phase, get_current_phase
from prompts.luna import build_system_prompt

# Config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "luna"),
    "password": os.getenv("DB_PASSWORD", "luna_password"),
    "database": os.getenv("DB_NAME", "luna_db"),
}
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_ID = 8346018933

# Test messages simulating a conversation
TEST_CONVERSATION = [
    # Phase HOOK (msgs 1-3)
    {"user": "Salut!", "luna": "Hey! 🧡 C'est qui?"},
    {"user": "Je m'appelle Lucas, et toi?", "luna": "Luna! Enchantée Lucas. Tu fais quoi dans la vie?"},
    {"user": "Je suis dev à Lyon, j'aime le gaming", "luna": "Dev à Lyon, pas mal! Moi aussi je game. Tu joues à quoi?"},

    # Phase CONNECT (msgs 4-6)
    {"user": "Valorant surtout, et toi?", "luna": "Omg Valorant! Je main Jett. On devrait jouer ensemble un jour"},
    {"user": "Carrément! T'es quel rank?", "luna": "Plat, j'essaie de monter. Et toi Lucas?"},
    {"user": "Diamond, je pourrai te carry mdr", "luna": "Mdrr trop confiant! On verra ça 😏"},

    # Phase ATTACH (msgs 7-9)
    {"user": "Tu fais quoi ce soir?", "luna": "Netflix avec Pixel (mon chat), la routine. Tu veux qu'on parle?"},
    {"user": "Ouais j'aime bien parler avec toi", "luna": "Aww c'est mignon 🧡 Moi aussi j'aime bien. Tu me manquais un peu"},
    {"user": "Mon frère Pierre dit que je parle trop de toi lol", "luna": "Haha Pierre a raison, tu parles de moi? C'est cute"},

    # Phase TENSION (msg 10+)
    {"user": "T'es vraiment belle Luna", "luna": "Merci bébé... Si t'étais là je sais pas ce que je ferais 🙈"},
]

# NSFW test messages (Phase LIBRE)
NSFW_TEST = {
    "user": "J'ai envie de toi Luna...",
    "luna": "Mmh moi aussi bébé... Viens contre moi 💕"
}


async def run_test():
    """Run the complete flow test."""
    print("=" * 70)
    print("🧪 TEST COMPLET DU FLOW LUNA")
    print("=" * 70)

    # Connect to DB
    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)
    set_memory_pool(pool)
    set_extraction_api_key(OPENROUTER_API_KEY)

    try:
        # Get user
        user = await get_or_create_user(TELEGRAM_ID)
        user_id = user["id"]
        print(f"\n👤 User: {user_id} (telegram: {TELEGRAM_ID})")

        relationship = await get_relationship(user_id)
        print(f"   Day: {relationship.get('day', 1)}, Msgs: {relationship.get('message_count', 0)}")

        # =====================================================================
        # TEST 1: HOOK PHASE (messages 1-3)
        # =====================================================================
        print("\n" + "=" * 70)
        print("📍 TEST 1: PHASE HOOK (messages 1-3)")
        print("=" * 70)

        for i, msg in enumerate(TEST_CONVERSATION[:3], 1):
            # Increment message count
            async with pool.acquire() as conn:
                msg_count = await conn.fetchval("""
                    UPDATE memory_relationships
                    SET message_count = COALESCE(message_count, 0) + 1
                    WHERE user_id = $1
                    RETURNING message_count
                """, user_id)

            # Get phase
            rel = await get_relationship(user_id)
            phase = get_current_phase(msg_count, rel.get("day", 1), rel.get("paid", False), rel.get("paywall_shown", False))

            print(f"\n   [{i}] User: {msg['user'][:50]}")
            print(f"       Luna: {msg['luna'][:50]}")
            print(f"       Phase: {phase.value} | Msgs: {msg_count}")

            # Extract memory
            result = await extract_unified(user_id, msg["user"], msg["luna"], [])
            if result.get("stored"):
                print(f"       📝 Extracted: {list(result['stored'].keys())}")

        # Check phase is HOOK
        rel = await get_relationship(user_id)
        phase = get_current_phase(rel.get("message_count", 0), rel.get("day", 1), False, False)
        assert phase == Phase.HOOK, f"Expected HOOK, got {phase}"
        print(f"\n   ✅ Phase HOOK confirmée")

        # =====================================================================
        # TEST 2: MEMORY ACCUMULATION (messages 4-10)
        # =====================================================================
        print("\n" + "=" * 70)
        print("📍 TEST 2: ACCUMULATION MÉMOIRE (messages 4-10)")
        print("=" * 70)

        for i, msg in enumerate(TEST_CONVERSATION[3:], 4):
            async with pool.acquire() as conn:
                msg_count = await conn.fetchval("""
                    UPDATE memory_relationships
                    SET message_count = COALESCE(message_count, 0) + 1
                    WHERE user_id = $1
                    RETURNING message_count
                """, user_id)

            rel = await get_relationship(user_id)
            phase = get_current_phase(msg_count, rel.get("day", 1), rel.get("paid", False), rel.get("paywall_shown", False))

            print(f"\n   [{i}] User: {msg['user'][:50]}")
            print(f"       Phase: {phase.value} | Msgs: {msg_count}")

            result = await extract_unified(user_id, msg["user"], msg["luna"], [])
            if result.get("stored"):
                print(f"       📝 Extracted: {list(result['stored'].keys())}")

        # Check memory accumulated
        print("\n   📊 Vérification mémoire accumulée:")

        user = await pool.fetchrow("SELECT * FROM memory_users WHERE telegram_id = $1", TELEGRAM_ID)
        print(f"      - Name: {user['name']}")
        print(f"      - Job: {user['job']}")
        print(f"      - Location: {user['location']}")
        print(f"      - Likes: {user['likes']}")
        print(f"      - Family: {user['family']}")

        rel = await get_relationship(user_id)
        jokes = rel.get("inside_jokes", [])
        print(f"      - Inside jokes: {len(jokes)}")

        timeline_count = await pool.fetchval("""
            SELECT COUNT(*) FROM memory_timeline WHERE user_id = $1
        """, user_id)
        print(f"      - Timeline events: {timeline_count}")

        # =====================================================================
        # TEST 3: PHASE LIBRE + NSFW
        # =====================================================================
        print("\n" + "=" * 70)
        print("📍 TEST 3: PHASE LIBRE + NSFW")
        print("=" * 70)

        # Force paid + advance day for LIBRE
        await update_relationship(user_id, {"paid": True, "paywall_shown": True})
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE memory_relationships
                SET day = 8, message_count = 100
                WHERE user_id = $1
            """, user_id)

        rel = await get_relationship(user_id)
        phase = get_current_phase(100, 8, True, True)
        print(f"\n   Phase: {phase.value} (day=8, paid=True, msgs=100)")
        assert phase == Phase.LIBRE, f"Expected LIBRE, got {phase}"
        print(f"   ✅ Phase LIBRE confirmée")

        # Test NSFW detection
        from luna_simple import is_nsfw_message, NSFW_KEYWORDS
        is_nsfw = is_nsfw_message(NSFW_TEST["user"])
        print(f"\n   🔥 NSFW Test: '{NSFW_TEST['user'][:30]}...'")
        print(f"      is_nsfw_message(): {is_nsfw}")

        # =====================================================================
        # TEST 4: MEMORY INJECTED IN NSFW
        # =====================================================================
        print("\n" + "=" * 70)
        print("📍 TEST 4: MÉMOIRE INJECTÉE EN NSFW")
        print("=" * 70)

        # Build memory context
        memory_context = await build_prompt_context(user_id, NSFW_TEST["user"])
        print(f"\n   📝 Memory context ({len(memory_context)} chars):")
        print("   " + "-" * 60)
        for line in memory_context.split("\n")[:15]:
            print(f"   {line}")
        if memory_context.count("\n") > 15:
            print(f"   ... ({memory_context.count(chr(10)) - 15} more lines)")
        print("   " + "-" * 60)

        # Build full NSFW prompt
        user_data = await pool.fetchrow("SELECT name FROM memory_users WHERE telegram_id = $1", TELEGRAM_ID)
        full_prompt = build_system_prompt(
            phase="LIBRE",
            user_name=user_data["name"],
            memory_context=memory_context,
            current_time="23h00",
            nsfw_allowed=True,
            nsfw_blocked_reason=None,
            mood=None
        )

        print(f"\n   📜 Full NSFW prompt ({len(full_prompt)} chars, ~{len(full_prompt)//4} tokens):")
        print("   " + "-" * 60)
        # Show key parts
        if "MÉMOIRE" in full_prompt or "CE QUE TU SAIS" in full_prompt:
            print("   ✅ Memory section présente")
        if "MODE INTIME" in full_prompt:
            print("   ✅ NSFW_ACTIVE modifier présent")
        if user_data["name"] and user_data["name"] in full_prompt:
            print(f"   ✅ User name ({user_data['name']}) injecté")
        print("   " + "-" * 60)

        # =====================================================================
        # FINAL SUMMARY
        # =====================================================================
        print("\n" + "=" * 70)
        print("📊 RÉSUMÉ FINAL")
        print("=" * 70)

        checks = {
            "Phase HOOK fonctionne": True,
            "Mémoire s'accumule": user['name'] is not None or timeline_count > 0,
            "Phase LIBRE accessible": phase == Phase.LIBRE,
            "NSFW detection": is_nsfw,
            "Mémoire injectée dans prompt": "MÉMOIRE" in full_prompt or "CE QUE TU SAIS" in full_prompt or len(memory_context) > 100,
            "NSFW modifier présent": "MODE INTIME" in full_prompt,
        }

        all_passed = True
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check}")
            if not passed:
                all_passed = False

        print("\n" + "=" * 70)
        if all_passed:
            print("🎉 TOUS LES TESTS PASSENT!")
        else:
            print("⚠️  CERTAINS TESTS ÉCHOUENT")
        print("=" * 70)

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_test())
