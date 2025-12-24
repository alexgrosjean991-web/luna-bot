"""Metrics tracking and JSON logging for Luna Bot."""
import json
import logging
import time


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        return json.dumps(log_data, ensure_ascii=False)


class Metrics:
    """Simple internal metrics tracker."""

    def __init__(self):
        self.messages_processed = 0
        self.errors_count = 0
        self.llm_calls = 0
        self.llm_errors = 0
        self.last_error: str | None = None
        self.last_error_time: float | None = None

    def record_message(self):
        self.messages_processed += 1

    def record_error(self, error: str):
        self.errors_count += 1
        self.last_error = error
        self.last_error_time = time.time()

    def record_llm_call(self, success: bool = True):
        self.llm_calls += 1
        if not success:
            self.llm_errors += 1

    def get_stats(self) -> dict:
        return {
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "llm_calls": self.llm_calls,
            "llm_errors": self.llm_errors,
            "llm_success_rate": f"{(1 - self.llm_errors / max(1, self.llm_calls)) * 100:.1f}%",
            "last_error": self.last_error,
        }


# Global singleton
metrics = Metrics()
