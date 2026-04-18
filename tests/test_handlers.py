"""Tests for handler-level user-visible behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.chat_commands import currentchat_command
from bot.handlers.text_messages import handle_text_message


class FakeFormattingService:
    """Formatting stub for handler tests."""

    def format_current_chat(self, chat) -> str:
        """Return a fixed message."""
        return "No active chat. Use /newchat or /chat <id>."


class FakeServices:
    """Minimal service container for handler tests."""

    def __init__(self) -> None:
        """Initialize fake dependencies."""
        self.chat_service = SimpleNamespace(get_active_chat=lambda user_id: None)
        self.formatting_service = FakeFormattingService()
        self.authorize_update = AsyncMock(return_value=True)


def make_context(services: FakeServices):
    """Create a fake Telegram context."""
    return SimpleNamespace(application=SimpleNamespace(bot_data={"services": services}), bot=AsyncMock())


def make_update():
    """Create a fake Telegram update with reply support."""
    message = SimpleNamespace(
        text="hello",
        message_id=99,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


async def test_text_handler_requires_active_chat() -> None:
    """Text messages without an active chat should be rejected safely."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)

    await handle_text_message(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "No active chat. Use /newchat or /chat <id>."
    )


async def test_currentchat_reports_no_active_chat() -> None:
    """The current chat command should return the formatter output."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)

    await currentchat_command(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "No active chat. Use /newchat or /chat <id>."
    )
