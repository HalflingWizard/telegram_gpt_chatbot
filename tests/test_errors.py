"""Tests for the global Telegram error handler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import NetworkError

from bot.handlers.errors import error_handler


async def test_network_error_is_treated_as_retryable_without_user_reply() -> None:
    """Transient Telegram network errors should not trigger a user-facing reply."""
    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=AsyncMock()))
    context = SimpleNamespace(error=NetworkError("boom"))

    await error_handler(update, context)

    update.effective_message.reply_text.assert_not_awaited()
