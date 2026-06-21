"""Structured logging configuration for the Telegram bot."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any


TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"/bot[0-9]+:[A-Za-z0-9_-]+")


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record into JSON."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_sensitive_text(record.getMessage()),
        }
        for field in (
            "telegram_user_id",
            "chat_public_id",
            "chat_db_id",
            "telegram_message_id",
            "action",
            "success",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = _redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str) -> None:
    """Configure root logging for the application."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)


def _redact_sensitive_text(text: str) -> str:
    """Remove secrets that can appear in third-party library logs."""
    return TELEGRAM_BOT_TOKEN_PATTERN.sub("/bot<redacted>", text)
