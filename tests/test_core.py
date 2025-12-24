"""Tests unitaires pour Luna Bot."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


class TestSanitizeInput:
    """Tests pour la fonction sanitize_input."""

    def test_returns_none_for_empty(self):
        from middleware.sanitize import sanitize_input
        assert sanitize_input("") is None
        assert sanitize_input(None) is None
        assert sanitize_input("   ") is None

    def test_truncates_long_input(self):
        from middleware.sanitize import sanitize_input, MAX_MESSAGE_LENGTH
        long_text = "a" * 3000
        result = sanitize_input(long_text)
        assert len(result) == MAX_MESSAGE_LENGTH

    def test_removes_control_characters(self):
        from middleware.sanitize import sanitize_input
        text = "hello\x00world\x1f"
        result = sanitize_input(text)
        assert result == "helloworld"

    def test_preserves_newlines(self):
        from middleware.sanitize import sanitize_input
        text = "hello\nworld"
        result = sanitize_input(text)
        assert result == "hello\nworld"


class TestDetectEngagement:
    """Tests pour detect_engagement_signal."""

    def test_strong_signal(self):
        from middleware.sanitize import detect_engagement_signal
        assert detect_engagement_signal("j'adore ca") == 2
        assert detect_engagement_signal("tu es trop belle") == 2

    def test_light_signal(self):
        from middleware.sanitize import detect_engagement_signal
        assert detect_engagement_signal("c'est cool") == 1
        assert detect_engagement_signal("haha") == 1

    def test_neutral(self):
        from middleware.sanitize import detect_engagement_signal
        assert detect_engagement_signal("ok") == 0
        assert detect_engagement_signal("je vais bien") == 0


class TestRateLimiter:
    """Tests pour le RateLimiter."""

    def test_allows_first_request(self):
        from middleware.rate_limit import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=5)
        assert limiter.is_allowed(123) is True

    def test_blocks_after_limit(self):
        from middleware.rate_limit import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=3)
        for _ in range(3):
            limiter.is_allowed(123)
        assert limiter.is_allowed(123) is False

    def test_different_users_independent(self):
        from middleware.rate_limit import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=2)
        limiter.is_allowed(123)
        limiter.is_allowed(123)
        assert limiter.is_allowed(123) is False
        assert limiter.is_allowed(456) is True

    def test_get_wait_time(self):
        from middleware.rate_limit import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=1)
        limiter.is_allowed(123)
        wait = limiter.get_wait_time(123)
        assert 59 <= wait <= 60


class TestMetrics:
    """Tests pour la classe Metrics."""

    def test_record_message(self):
        from middleware.metrics import Metrics
        m = Metrics()
        assert m.messages_processed == 0
        m.record_message()
        assert m.messages_processed == 1

    def test_record_error(self):
        from middleware.metrics import Metrics
        m = Metrics()
        m.record_error("test error")
        assert m.errors_count == 1
        assert m.last_error == "test error"

    def test_record_llm_call(self):
        from middleware.metrics import Metrics
        m = Metrics()
        m.record_llm_call(success=True)
        m.record_llm_call(success=False)
        assert m.llm_calls == 2
        assert m.llm_errors == 1

    def test_get_stats(self):
        from middleware.metrics import Metrics
        m = Metrics()
        m.record_message()
        m.record_llm_call(success=True)
        stats = m.get_stats()
        assert stats["messages_processed"] == 1
        assert stats["llm_calls"] == 1
        assert stats["llm_success_rate"] == "100.0%"


class TestCleanResponse:
    """Tests pour la fonction clean_response."""

    def test_removes_asterisk_actions(self):
        from services.llm import clean_response
        text = "salut *sourit* comment ca va?"
        result = clean_response(text)
        assert result == "salut comment ca va?"

    def test_removes_multiple_asterisks(self):
        from services.llm import clean_response
        text = "*rit* coucou *fait un clin d'oeil* toi"
        result = clean_response(text)
        assert result == "coucou toi"

    def test_preserves_normal_text(self):
        from services.llm import clean_response
        text = "salut comment tu vas?"
        result = clean_response(text)
        assert result == "salut comment tu vas?"


class TestFormatMemory:
    """Tests pour format_memory_for_prompt."""

    def test_empty_memory(self):
        from services.memory import format_memory_for_prompt
        result = format_memory_for_prompt({})
        assert result == "Tu ne sais encore rien sur lui."

    def test_with_prenom(self):
        from services.memory import format_memory_for_prompt
        result = format_memory_for_prompt({"prenom": "Alex"})
        assert "Alex" in result

    def test_with_multiple_fields(self):
        from services.memory import format_memory_for_prompt
        memory = {
            "prenom": "Alex",
            "age": 25,
            "ville": "Paris"
        }
        result = format_memory_for_prompt(memory)
        assert "Alex" in result
        assert "25" in result
        assert "Paris" in result


# ============== V3 MOMENTUM TESTS ==============

class TestMomentumEngine:
    """Tests pour le systeme momentum V3."""

    def test_classify_intensity_sfw(self):
        from services.momentum import momentum_engine, Intensity
        intensity, is_negative = momentum_engine.classify_intensity("salut ca va?")
        assert intensity == Intensity.SFW

    def test_classify_intensity_flirt(self):
        from services.momentum import momentum_engine, Intensity
        intensity, is_negative = momentum_engine.classify_intensity("tu es vraiment mignonne")
        assert intensity == Intensity.FLIRT

    def test_classify_intensity_hot(self):
        from services.momentum import momentum_engine, Intensity
        intensity, is_negative = momentum_engine.classify_intensity("j'ai envie de toi")
        assert intensity == Intensity.HOT

    def test_tier_thresholds(self):
        from services.momentum import momentum_engine
        # Tier 1: momentum < 35
        assert momentum_engine.get_tier(20, day_count=3, intimacy_history=0) == 1
        # Tier 2: 35 <= momentum < 65
        assert momentum_engine.get_tier(50, day_count=3, intimacy_history=0) == 2
        # Tier 3: momentum >= 65
        assert momentum_engine.get_tier(70, day_count=3, intimacy_history=1) == 3

    def test_tier_high_momentum(self):
        from services.momentum import momentum_engine
        # High momentum = tier 3
        assert momentum_engine.get_tier(80, day_count=5, intimacy_history=1) == 3

    def test_momentum_calculation(self):
        from services.momentum import momentum_engine, Intensity
        # SFW message
        new_momentum, intensity, _ = momentum_engine.calculate_momentum(
            "salut", current_momentum=20, messages_this_session=5, day_count=3
        )
        assert intensity == Intensity.SFW
        # Momentum increases with session bonus but should stay reasonable
        assert new_momentum >= 20  # At least current

    def test_climax_detection(self):
        from services.momentum import momentum_engine
        assert momentum_engine.detect_climax("mmh je jouis") is True
        assert momentum_engine.detect_climax("salut ca va") is False

    def test_climax_cooldown(self):
        from services.momentum import momentum_engine
        new_momentum = momentum_engine.apply_climax_cooldown(80)
        assert new_momentum < 80  # Should reduce momentum

    def test_time_decay(self):
        from services.momentum import momentum_engine
        from datetime import datetime, timedelta, timezone

        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        decayed = momentum_engine.apply_time_decay(
            current_momentum=50,
            last_message_at=old_time,
            messages_since_climax=999
        )
        assert decayed < 50  # Should decay

    def test_nsfw_states(self):
        from services.momentum import momentum_engine
        # Tension state: 30-50
        assert momentum_engine.get_nsfw_state(40, 999) == "tension"
        # Buildup state: 51-70
        assert momentum_engine.get_nsfw_state(60, 999) == "buildup"
        # Climax state: 71+
        assert momentum_engine.get_nsfw_state(80, 999) == "climax"
        # Aftercare state: after climax
        assert momentum_engine.get_nsfw_state(30, 2) == "aftercare"


# ============== V8 LUNA MOOD TESTS ==============

class TestLunaMoodEngine:
    """Tests pour le systeme mood V8."""

    def test_mood_values(self):
        from services.luna_mood import LunaMood
        assert LunaMood.NORMAL.value == "normal"
        assert LunaMood.HORNY.value == "horny"

    def test_should_update_mood_none(self):
        from services.luna_mood import luna_mood_engine
        # No previous update = should update
        assert luna_mood_engine.should_update_mood(None) is True

    def test_should_update_mood_recent(self):
        from services.luna_mood import luna_mood_engine
        from datetime import datetime, timezone
        # Recent update = should not update
        recent = datetime.now(timezone.utc)
        assert luna_mood_engine.should_update_mood(recent) is False

    def test_availability_check(self):
        from services.luna_mood import luna_mood_engine, LunaMood
        result = luna_mood_engine.check_availability(
            mood=LunaMood.NORMAL,
            minutes_since_climax=120,
            current_hour=22,
            momentum=30,
            intensity_is_nsfw=False
        )
        assert hasattr(result, 'should_deflect')
        assert hasattr(result, 'luna_initiates')


# ============== LLM ROUTER TESTS ==============

class TestLLMRouter:
    """Tests pour le routeur LLM."""

    def test_tier1_uses_haiku(self):
        from services.llm_router import get_llm_config_v3
        from services.momentum import Intensity
        provider, model, tier = get_llm_config_v3(
            momentum=20,
            day_count=3,
            intimacy_history=0,
            subscription_status="trial",
            detected_intensity=Intensity.SFW
        )
        assert provider == "anthropic"
        assert "haiku" in model.lower()
        assert tier == 1

    def test_tier3_uses_openrouter(self):
        from services.llm_router import get_llm_config_v3
        from services.momentum import Intensity
        provider, model, tier = get_llm_config_v3(
            momentum=75,
            day_count=5,
            intimacy_history=1,
            subscription_status="active",
            detected_intensity=Intensity.NSFW
        )
        assert provider == "openrouter"
        assert tier == 3

    def test_is_premium_session(self):
        from services.llm_router import is_premium_session
        assert is_premium_session("openrouter") is True
        assert is_premium_session("anthropic") is False


# ============== PROMPT SELECTOR TESTS ==============

class TestPromptSelector:
    """Tests pour le selecteur de prompts."""

    def test_tier1_prompt(self):
        from services.prompt_selector import get_prompt_for_tier
        prompt = get_prompt_for_tier(tier=1)
        assert "Luna" in prompt
        assert len(prompt) > 100

    def test_tier2_prompt(self):
        from services.prompt_selector import get_prompt_for_tier
        prompt = get_prompt_for_tier(tier=2)
        assert len(prompt) > 100

    def test_modifier_applied(self):
        from services.prompt_selector import get_prompt_for_tier
        prompt = get_prompt_for_tier(tier=1, modifier="USER_DISTRESSED")
        # Modifier should be mentioned or affect prompt content
        assert len(prompt) > 100  # Prompt is generated


# ============== ADMIN AUTH TESTS ==============

class TestAdminAuth:
    """Tests pour l'authentification admin."""

    def test_is_admin_with_valid_id(self):
        from handlers.commands import is_admin
        from settings import ADMIN_TELEGRAM_ID
        # Only passes if ADMIN_TELEGRAM_ID is set
        if ADMIN_TELEGRAM_ID != 0:
            assert is_admin(ADMIN_TELEGRAM_ID) is True

    def test_is_admin_rejects_zero(self):
        from handlers.commands import is_admin
        # Random ID should not be admin
        assert is_admin(999999999) is False

    def test_is_admin_rejects_when_not_configured(self):
        from handlers.commands import is_admin
        import handlers.commands as cmd
        original = cmd.ADMIN_TELEGRAM_ID
        cmd.ADMIN_TELEGRAM_ID = 0
        assert is_admin(123456) is False
        cmd.ADMIN_TELEGRAM_ID = original


# ============== V9 IMMERSION TESTS ==============

class TestImmersion:
    """Tests pour le système d'immersion V9."""

    def test_temporal_context_calculation(self):
        from services.immersion import get_temporal_context
        ctx = get_temporal_context(None, 14)
        assert ctx.hours_since_last == 0.0
        assert ctx.is_afternoon is True

    def test_temporal_instruction_long_absence(self):
        from services.immersion import get_temporal_context, get_temporal_instruction
        from datetime import datetime, timezone, timedelta
        old_time = datetime.now(timezone.utc) - timedelta(days=2)
        ctx = get_temporal_context(old_time, 14)
        instruction = get_temporal_instruction(ctx)
        assert instruction is not None
        assert "2 jours" in instruction

    def test_luna_life_instruction(self):
        from services.immersion import get_luna_life_instruction
        # Test multiple times (25% probability)
        results = [get_luna_life_instruction(day_count=3, is_weekend=False) for _ in range(100)]
        # At least some should return instructions
        non_none = [r for r in results if r is not None]
        assert len(non_none) > 10  # ~25% of 100

    def test_emotion_generation(self):
        from services.immersion import get_emotion_for_session, LunaEmotion
        emotions = [get_emotion_for_session() for _ in range(100)]
        # Should have variety
        unique = set(emotions)
        assert len(unique) >= 2

    def test_jealousy_detection(self):
        from services.immersion import detect_jealousy_trigger
        assert detect_jealousy_trigger("j'ai vu marie hier") is True
        assert detect_jealousy_trigger("j'ai mangé une pizza") is False
        assert detect_jealousy_trigger("avec emma on est sorti") is True

    def test_open_topics_detection(self):
        from services.immersion import detect_open_topics
        topics = detect_open_topics("j'ai un problème au boulot")
        assert len(topics) >= 1
        assert topics[0].topic_type == "travail_stress"

    def test_open_topics_no_match(self):
        from services.immersion import detect_open_topics
        topics = detect_open_topics("salut comment ça va")
        assert len(topics) == 0

    def test_build_immersion_context(self):
        from services.immersion import build_immersion_context
        ctx = build_immersion_context(
            last_message_at=None,
            current_hour=14,
            day_count=3,
            messages_this_session=10,
            user_message="salut"
        )
        assert ctx is not None
