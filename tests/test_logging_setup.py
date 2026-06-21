"""Tests for structured logging helpers."""

import json
import logging

from bot.logging_setup import JsonFormatter


def test_json_formatter_redacts_telegram_bot_token() -> None:
    """Telegram tokens in library log messages should not be printed."""
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="POST https://api.telegram.org/bot123456:ABC_def-GHI/sendMessage",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert "bot123456:ABC_def-GHI" not in payload["message"]
    assert "/bot<redacted>/sendMessage" in payload["message"]
