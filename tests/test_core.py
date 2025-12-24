"""Tests unitaires pour Luna Bot."""
import pytest
import time


class TestSanitizeInput:
    """Tests pour la fonction sanitize_input."""

    def test_returns_none_for_empty(self):
        from bot import sanitize_input
        assert sanitize_input("") is None
        assert sanitize_input(None) is None
        assert sanitize_input("   ") is None

    def test_truncates_long_input(self):
        from bot import sanitize_input, MAX_MESSAGE_LENGTH
        long_text = "a" * 3000
        result = sanitize_input(long_text)
        assert len(result) == MAX_MESSAGE_LENGTH

    def test_removes_control_characters(self):
        from bot import sanitize_input
        text = "hello\x00world\x1f"
        result = sanitize_input(text)
        assert result == "helloworld"

    def test_preserves_newlines(self):
        from bot import sanitize_input
        text = "hello\nworld"
        result = sanitize_input(text)
        assert result == "hello\nworld"


class TestRateLimiter:
    """Tests pour le RateLimiter."""

    def test_allows_first_request(self):
        from bot import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=5)
        assert limiter.is_allowed(123) is True

    def test_blocks_after_limit(self):
        from bot import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=3)
        for _ in range(3):
            limiter.is_allowed(123)
        assert limiter.is_allowed(123) is False

    def test_different_users_independent(self):
        from bot import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=2)
        limiter.is_allowed(123)
        limiter.is_allowed(123)
        assert limiter.is_allowed(123) is False
        assert limiter.is_allowed(456) is True

    def test_get_wait_time(self):
        from bot import RateLimiter
        limiter = RateLimiter(window_seconds=60, max_requests=1)
        limiter.is_allowed(123)
        wait = limiter.get_wait_time(123)
        assert 59 <= wait <= 60


class TestCleanResponse:
    """Tests pour la fonction clean_response."""

    def test_removes_asterisk_actions(self):
        from services.llm import clean_response
        text = "salut *sourit* comment ça va?"
        result = clean_response(text)
        assert result == "salut comment ça va?"

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


class TestMetrics:
    """Tests pour la classe Metrics."""

    def test_record_message(self):
        from bot import Metrics
        m = Metrics()
        assert m.messages_processed == 0
        m.record_message()
        assert m.messages_processed == 1

    def test_record_error(self):
        from bot import Metrics
        m = Metrics()
        m.record_error("test error")
        assert m.errors_count == 1
        assert m.last_error == "test error"

    def test_record_llm_call(self):
        from bot import Metrics
        m = Metrics()
        m.record_llm_call(success=True)
        m.record_llm_call(success=False)
        assert m.llm_calls == 2
        assert m.llm_errors == 1

    def test_get_stats(self):
        from bot import Metrics
        m = Metrics()
        m.record_message()
        m.record_llm_call(success=True)
        stats = m.get_stats()
        assert stats["messages_processed"] == 1
        assert stats["llm_calls"] == 1
        assert stats["llm_success_rate"] == "100.0%"
